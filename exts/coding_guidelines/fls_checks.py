# SPDX-License-Identifier: MIT OR Apache-2.0
# SPDX-FileCopyrightText: The Coding Guidelines Subcommittee Contributors


import json
import re
import time

import requests
from sphinx.errors import SphinxError
from sphinx_needs.data import SphinxNeedsData

from . import fls_diff
from .common import bar_format, get_tqdm, logger

fls_paragraph_ids_url = "https://rust-lang.github.io/fls/paragraph-ids.json"
FLS_FETCH_TIMEOUT = (5, 30)
FLS_FETCH_RETRY_DELAYS = (1, 2)
# Contributor builds fall back promptly; enforcing gates wait out ordinary CDN throttling.
FLS_FETCH_NONBLOCKING_RETRY_BUDGET_SECONDS = 3
FLS_FETCH_ENFORCING_RETRY_BUDGET_SECONDS = 60


class FLSValidationError(SphinxError):
    category = "FLS Validation Error"


def record_fls_notice(app, message):
    notices = getattr(app, "fls_notices", None)
    if notices is None:
        notices = []
        app.fls_notices = notices
    notices.append(message)


def fetch_live_fls_data(
    json_url, *, retry_budget_seconds=FLS_FETCH_NONBLOCKING_RETRY_BUDGET_SECONDS
):
    retry_sleep = 0
    for attempt in range(len(FLS_FETCH_RETRY_DELAYS) + 1):
        try:
            response = requests.get(json_url, timeout=FLS_FETCH_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (json.JSONDecodeError, ValueError) as error:
            logger.info("Unable to parse live FLS data from %s: %s", json_url, error)
            return None
        except requests.RequestException as error:
            response = getattr(error, "response", None)
            status = getattr(response, "status_code", None)
            retryable = isinstance(error, (requests.ConnectionError, requests.Timeout)) or (
                isinstance(error, requests.HTTPError)
                and status is not None
                and (status == 429 or status >= 500)
            )
            if not retryable or attempt == len(FLS_FETCH_RETRY_DELAYS):
                logger.info("Unable to retrieve live FLS data from %s: %s", json_url, error)
                return None
            delay = FLS_FETCH_RETRY_DELAYS[attempt]
            if status in (429, 503):
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        parsed_delay = int(retry_after)
                    except ValueError:
                        pass
                    else:
                        if parsed_delay >= 0:
                            delay = parsed_delay
            remaining = retry_budget_seconds - retry_sleep
            if delay > remaining:
                logger.info(
                    "Live FLS retry delay of %s seconds exceeds the "
                    "%s-second remaining budget",
                    delay,
                    remaining,
                )
                return None
            logger.info("Live FLS request failed; retrying in %s second(s): %s", delay, error)
            time.sleep(delay)
            retry_sleep += delay
    raise AssertionError("unreachable")


def check_fls(app, env):
    """Main checking function for FLS validation"""
    # First make sure all guidelines have correctly formatted FLS IDs
    #
    check_fls_exists_and_valid_format(app, env)
    offline_mode = env.config.offline
    enforce_freshness = app.config.enable_spec_lock_consistency
    json_url = app.config.fls_paragraph_ids_url

    # Gather all FLS paragraph IDs from the specification and get the raw JSON
    fls_ids, raw_json_data = gather_fls_paragraph_ids(app, json_url, offline=offline_mode)
    freshness_available = True
    if not raw_json_data:
        if not offline_mode and not enforce_freshness:
            fls_ids, raw_json_data = gather_fls_paragraph_ids(
                app, json_url, offline=True
            )
            freshness_available = False
            if raw_json_data:
                record_fls_notice(
                    app,
                    "Live FLS unavailable or unusable; freshness was not checked. "
                    "References were validated against the committed src/spec.lock.",
                )
        if not raw_json_data:
            if offline_mode:
                error_message = f"Failed to read or parse the committed FLS lock at {app.confdir / 'spec.lock'}"
            elif not enforce_freshness:
                error_message = (
                    "Failed to retrieve the live FLS and read or parse the committed "
                    f"FLS lock at {app.confdir / 'spec.lock'}"
                )
            else:
                error_message = (
                    "Failed to retrieve or parse the FLS specification from "
                    f"{json_url}"
                )
            logger.error(error_message)
            raise FLSValidationError(error_message)

    app.fls_urls = {
        fls_id: metadata["url"]
        for fls_id, metadata in fls_ids.items()
        if metadata.get("url")
    }

    if not offline_mode and freshness_available:
        # Check for differences against lock file
        has_differences, differences = check_fls_lock_consistency(
            app, env, raw_json_data
        )
        if has_differences:
            if not enforce_freshness:
                has_differences = False
        if has_differences:
            error_message = (
                "The FLS specification has changed since the lock file was created:\n"
            )
            for diff in differences:
                error_message += f"  - {diff}\n"
            error_message += "\nPlease manually inspect FLS spec items whose checksums have changed as corresponding guidelines may need to account for these changes."
            error_message += "\nTo review a structured audit report, run:"
            error_message += "\n\tuv run python scripts/fls_audit.py"
            error_message += "\nIf the audit tool reports missing baseline metadata, provide --baseline-fls-commit/--current-fls-commit or set GITHUB_TOKEN when using deployment offsets."
            error_message += "\nOnce resolved, you may run the following to update the local spec lock file:"
            error_message += "\n\tuv run --frozen make.py --update-spec-lock-file"
            logger.error(error_message)
            raise FLSValidationError(error_message)
    # Check if all referenced FLS IDs exist
    check_fls_ids_correct(app, env, fls_ids)

    # Read the ignore list
    fls_id_ignore_list = read_fls_ignore_list(app)

    # Insert coverage information into fls_ids
    insert_fls_coverage(app, env, fls_ids)

    # Calculate and report coverage
    coverage_data = calculate_fls_coverage(fls_ids, fls_id_ignore_list)

    # Log coverage report
    log_coverage_report(coverage_data)


def read_fls_ignore_list(app):
    """Read the list of FLS IDs to ignore from a file"""
    ignore_file_path = app.confdir / "spec_ignore_list.txt"
    ignore_list = []

    if ignore_file_path.exists():
        logger.info(f"Reading FLS ignore list from {ignore_file_path}")
        with open(ignore_file_path, "r") as f:
            for line in f:
                # Remove comments and whitespace
                line = line.split("#")[0].strip()
                if line:
                    ignore_list.append(line)
        logger.info(f"Loaded {len(ignore_list)} FLS IDs to ignore")
    else:
        logger.warning(f"No FLS ignore list found at {ignore_file_path}")

    return ignore_list


def check_fls_exists_and_valid_format(app, env):
    logger.debug("check_fls_exists_and_valid_format")

    data = SphinxNeedsData(env)

    needs = data.get_needs_view()
    logger.debug(f"Checking needs {needs!r}")

    # Regular expression for FLS ID validation
    # Format: fls_<12 alphanumeric chars including upper and lowercase>
    fls_pattern = re.compile(r"^fls_[a-zA-Z0-9]{9,12}$")

    for need_id, need in needs.items():
        logger.debug(f"ID: {need_id}, Need: {need}")
        if need.get("type") == "guideline":
            fls_value = need.get("fls")

            # Check if fls field exists and is not empty
            if fls_value is None:
                msg = f"Need {need_id} has no fls field"
                logger.error(msg)
                raise FLSValidationError(msg)

            if fls_value == "":
                msg = f"Need {need_id} has empty fls field"
                logger.error(msg)
                raise FLSValidationError(msg)

            # Validate FLS ID format
            if not fls_pattern.match(fls_value):
                msg = f"Need {need_id} has invalid fls format: '{fls_value}'. Expected format: fls_ followed by 12 alphanumeric characters"
                logger.error(msg)
                raise FLSValidationError(msg)


def check_fls_ids_correct(app, env, fls_ids):
    """
    Check that all FLS IDs referenced in guidelines actually exist in the specification.

    Args:
        app: The Sphinx application
        env: The Sphinx environment
        fls_ids: Dictionary of FLS paragraph IDs mapped to their source URLs
    """
    logger.debug("check_fls_ids_correct")
    data = SphinxNeedsData(env)
    needs = data.get_needs_view()

    # Track any errors found
    invalid_ids = []

    # prefiltering: this is mainly done for tqdm progress
    guidelines = {k: v for k, v in needs.items() if v.get("type") == "guideline"}

    pbar = get_tqdm(
        iterable=guidelines.items(),
        desc="Validating FLS IDs",
        bar_format=bar_format,
        unit="need",
    )

    # Check each guideline's FLS reference
    for need_id, need in pbar:
        if need.get("type") == "guideline":
            pbar.set_postfix(fls_id=need_id)
            fls_value = need.get("fls")

            # Skip needs we already validated format for
            if fls_value is None or fls_value == "":
                continue

            # Check if the FLS ID exists in the gathered IDs
            if fls_value not in fls_ids:
                invalid_ids.append((need_id, fls_value))
                logger.warning(
                    f"Need {need_id} references non-existent FLS ID: '{fls_value}'"
                )

        # Raise error if any invalid IDs were found
        if invalid_ids:
            error_message = "The following needs reference non-existent FLS IDs:\n"
            for need_id, fls_id in invalid_ids:
                error_message += f"  - Need {need_id} references '{fls_id}'\n"
            logger.error(error_message)
            raise FLSValidationError(error_message)

    logger.info("All FLS references in guidelines are valid")

    pbar.close()  # Ensure cleanup


def gather_fls_paragraph_ids(app, json_url, *, offline=None):
    """
    Gather all FLS paragraph IDs from the paragraph-ids.json file
    or from the lock file in offline mode, including both container section IDs and individual paragraph IDs.

    Args:
        app: The Sphinx application
        json_url: The URL or path to the paragraph-ids.json file

    Returns:
        Dictionary mapping paragraph IDs to metadata AND the complete raw JSON data
    """
    offline_mode = app.config.offline if offline is None else offline
    lock_path = app.confdir / "spec.lock"

    # Dictionary to store all FLS IDs and their metadata
    all_fls_ids = {}
    raw_json_data = None

    try:
        # Load the JSON file
        if not offline_mode:
            logger.info("Gathering FLS paragraph IDs from %s", json_url)
            retry_budget_seconds = (
                FLS_FETCH_ENFORCING_RETRY_BUDGET_SECONDS
                if app.config.enable_spec_lock_consistency
                else FLS_FETCH_NONBLOCKING_RETRY_BUDGET_SECONDS
            )
            raw_json_data = fetch_live_fls_data(
                json_url, retry_budget_seconds=retry_budget_seconds
            )
            if raw_json_data is None:
                return {}, None
            data = raw_json_data
            logger.debug("Successfully parsed JSON data")

        else:  # if online mode is on read from the lock file
            if not lock_path.exists():
                logger.error(f"No FLS lock file found at {lock_path}")
                return {}, None
            logger.info("Gathering FLS paragraph IDs from lock file: %s", lock_path)
            with open(lock_path, "r", encoding="utf-8") as f:
                raw_json_data = f.read()
                data = json.loads(raw_json_data)

        # Check if we have the expected document structure
        documents = data.get("documents") if isinstance(data, dict) else None
        if not isinstance(documents, list) or not documents:
            log = logger.error if offline_mode else logger.info
            log("FLS data does not contain a nonempty 'documents' list")
            return {}, None

        # Base URL for constructing direct links
        base_url = "https://rust-lang.github.io/fls/"

        # Process each document in the JSON structure
        for document in documents:
            doc_title = document.get("title", "Unknown")

            # Process each section in the document
            for section in document.get("sections", []):
                section_title = section.get("title", "Unknown")
                section_id = section.get("id", "")
                section_number = section.get("number", "")
                section_link = section.get("link", "")
                is_informational = section.get("informational", False)

                # Add the section container ID if it starts with 'fls_'
                if section_id and section_id.startswith("fls_"):
                    direct_url = f"{base_url}{section_link}"

                    # Store section metadata
                    all_fls_ids[section_id] = {
                        "url": direct_url,
                        "section_id": section_number,
                        "document_title": doc_title,
                        "section_title": section_title,
                        "section_number": section_number,
                        "is_container": True,  # Mark as a container/section
                        "informational": is_informational,
                        # Note: No checksum for container IDs
                    }

                # Process each paragraph in the section
                for paragraph in section.get("paragraphs", []):
                    para_id = paragraph.get("id", "")
                    para_number = paragraph.get("number", "")
                    para_link = paragraph.get("link", "")
                    para_checksum = paragraph.get("checksum", "")

                    # Skip entries without proper IDs
                    if not para_id or not para_id.startswith("fls_"):
                        continue

                    # Create the full URL
                    direct_url = f"{base_url}{para_link}"

                    # Store metadata
                    all_fls_ids[para_id] = {
                        "url": direct_url,
                        "section_id": para_number,
                        "document_title": doc_title,
                        "section_title": section_title,
                        "section_number": section_number,
                        "checksum": para_checksum,
                        "is_container": False,  # Mark as individual paragraph
                        "parent_section_id": section_id if section_id else None,
                    }

        if not all_fls_ids:
            log = logger.error if offline_mode else logger.info
            log("FLS data does not contain any usable section or paragraph IDs")
            return {}, None

        logger.info(f"Found {len(all_fls_ids)} total FLS IDs (sections and paragraphs)")
        # Count sections vs paragraphs
        sections_count = sum(
            1
            for metadata in all_fls_ids.values()
            if metadata.get("is_container", False)
        )
        paragraphs_count = len(all_fls_ids) - sections_count
        logger.info(f"  - {sections_count} section/container IDs")
        logger.info(f"  - {paragraphs_count} paragraph IDs")

        return all_fls_ids, raw_json_data

    # Upstream schema drift makes live data unusable; check_fls decides whether
    # that is fatal or whether the build can fall back to the committed lock.
    except (json.JSONDecodeError, OSError, AttributeError, TypeError, ValueError) as error:
        source = lock_path if offline_mode else json_url
        log = logger.error if offline_mode else logger.info
        log("Failed to parse FLS data from %s: %s", source, error)
        return {}, None


def check_fls_lock_consistency(app, env, fls_raw_data):
    """
    Compare live FLS JSON data with the lock file to detect changes

    Args:
        app: The Sphinx application
        env: The Sphinx environment
        fls_raw_data: Raw JSON data from the live specification

    Returns:
        Tuple containing:
        - Boolean indicating whether differences were found
        - List of difference descriptions with affected guidelines (for error reporting)
    """
    logger.info("Checking FLS lock file consistency")
    lock_path = app.confdir / "spec.lock"

    if not lock_path.exists():
        error_message = f"No FLS lock file found at {lock_path}"
        logger.error(error_message)
        raise FLSValidationError(error_message)

    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            locked_data = json.load(f)
    except (json.JSONDecodeError, OSError) as error:
        error_message = f"Failed to read FLS lock file {lock_path}: {error}"
        logger.error(error_message)
        raise FLSValidationError(error_message) from error
    documents = locked_data.get("documents") if isinstance(locked_data, dict) else None
    if not isinstance(documents, list) or not documents:
        error_message = f"Invalid FLS lock file {lock_path}: documents must be a nonempty list"
        logger.error(error_message)
        raise FLSValidationError(error_message)

    # Get the needs data to find affected guidelines
    data = SphinxNeedsData(env)
    needs = data.get_needs_view()

    # Map of FLS IDs to guidelines that reference them
    fls_to_guidelines = {}

    # prefiltering: this is mainly done for tqdm progress
    guidelines = {k: v for k, v in needs.items() if v.get("type") == "guideline"}
    pbar = get_tqdm(
        iterable=guidelines.items(),
        desc="Checking fls lock consistency",
        bar_format=bar_format,
        unit="need",
    )

    for need_id, need in pbar:
        if need.get("type") == "guideline":
            pbar.set_postfix(fls_id=need_id)
            fls_value = need.get("fls")
            if fls_value:
                if fls_value not in fls_to_guidelines:
                    fls_to_guidelines[fls_value] = []
                fls_to_guidelines[fls_value].append(
                    {"id": need_id, "title": need.get("title", "Untitled")}
                )

    try:
        live_paragraphs = fls_diff.extract_paragraphs(fls_raw_data)
        locked_paragraphs = fls_diff.extract_paragraphs(locked_data)
        if not locked_paragraphs:
            raise ValueError("the lock contains no FLS paragraphs")

        logger.info(f"Found {len(live_paragraphs)} paragraphs in live data")
        logger.info(f"Found {len(locked_paragraphs)} paragraphs in lock file")

        diff = fls_diff.diff_paragraphs(live_paragraphs, locked_paragraphs)
        has_differences = fls_diff.has_differences(diff)
        detailed_differences, affected_guidelines = (
            fls_diff.build_detailed_differences(diff, fls_to_guidelines)
        )

        temp_path = None
        report_unavailable = False
        if has_differences:
            try:
                temp_path = fls_diff.write_detailed_report(detailed_differences)
                log = logger.warning if app.config.enable_spec_lock_consistency else logger.info
                log(f"Detailed FLS differences written to: {temp_path}")
            except Exception as error:
                log = logger.warning if app.config.enable_spec_lock_consistency else logger.info
                log(f"Failed to write detailed differences to temp file: {error}")
                report_unavailable = True

            if not app.config.enable_spec_lock_consistency:
                if temp_path:
                    details = f" Details: {temp_path}."
                elif report_unavailable:
                    details = " Detailed report unavailable."
                else:
                    details = ""
                record_fls_notice(
                    app,
                    "spec.lock drift detected; build continued "
                    f"(added: {len(diff['added'])}, removed: {len(diff['removed'])}, "
                    f"changed: {len(diff['changed'])}).{details} "
                    "Run `uv run --frozen make.py --enforce-spec-lock-diff` to make this blocking.",
                )

        summary = fls_diff.build_summary(affected_guidelines, has_differences)

        return has_differences, summary

    except (TypeError, ValueError, KeyError) as error:
        error_message = f"Invalid FLS lock file {lock_path}: {error}"
        logger.error(error_message)
        raise FLSValidationError(error_message) from error


def insert_fls_coverage(app, env, fls_ids):
    """
    Enrich the fls_ids with whether each FLS ID is covered by coding guidelines

    Args:
        app: The Sphinx application
        env: The Sphinx environment
        fls_ids: Dictionary of FLS paragraph IDs with metadata
    """
    logger.debug("Inserting FLS coverage data")
    data = SphinxNeedsData(env)
    needs = data.get_needs_view()

    # Initialize coverage for all FLS IDs
    for fls_id in fls_ids:
        fls_ids[fls_id]["covered"] = False
        fls_ids[fls_id]["covering_needs"] = []  # List to store all covering guidelines

        # Extract chapter information from section_id (e.g., "22.1:4" -> chapter 22)
        section_id = fls_ids[fls_id]["section_id"]
        logger.debug(f"Processing section_id: {section_id} for {fls_id}")

        # Handle formats like "22.1:4", "4.3.1:9", or "A.1:2"
        if ":" in section_id:
            # Split at colon to get the section number without paragraph number
            section_parts = section_id.split(":")[0].split(".")
        else:
            # Fallback if no colon present
            section_parts = section_id.split(".")

        if section_parts and section_parts[0].isdigit():
            chapter = int(section_parts[0])
            fls_ids[fls_id]["chapter"] = chapter
        else:
            # Handle appendices or other non-standard formats
            first_char = section_id[0] if section_id else None
            if first_char and first_char.isalpha():
                # For appendices like "A.1.1", use the letter as chapter
                fls_ids[fls_id]["chapter"] = first_char
            else:
                fls_ids[fls_id]["chapter"] = "unknown"

    # Mark covered FLS IDs
    unique_covered_ids = set()
    total_references = 0

    for need_id, need in needs.items():
        if need.get("type") == "guideline":
            fls_value = need.get("fls")
            if fls_value and fls_value in fls_ids:
                fls_ids[fls_value]["covered"] = True
                fls_ids[fls_value]["covering_needs"].append(need_id)
                unique_covered_ids.add(fls_value)
                total_references += 1

    logger.info(f"Found {total_references} references to FLS IDs in guidelines")
    logger.info(f"Found {len(unique_covered_ids)} unique FLS IDs covered by guidelines")
    return fls_ids


def calculate_fls_coverage(fls_ids, fls_id_ignore_list):
    """
    Calculate coverage statistics for FLS IDs

    Args:
        fls_ids: Dictionary of FLS paragraph IDs with metadata, including coverage status
        fls_id_ignore_list: List of FLS IDs to ignore in coverage calculations

    Returns:
        Dictionary containing coverage statistics
    """
    logger.debug("Calculating FLS coverage statistics")

    # Track statistics
    total_ids = 0
    covered_ids = 0
    ignored_ids = 0

    # Organize by chapter
    chapters = {}

    # Process each FLS ID
    for fls_id, metadata in fls_ids.items():
        chapter = metadata.get("chapter", "unknown")

        # Initialize chapter data if needed
        if chapter not in chapters:
            chapters[chapter] = {"total": 0, "covered": 0, "ignored": 0, "ids": []}

        # Add to chapter's ID list
        chapters[chapter]["ids"].append(fls_id)
        chapters[chapter]["total"] += 1
        total_ids += 1

        # Check if ID should be ignored
        if fls_id in fls_id_ignore_list:
            ignored_ids += 1
            chapters[chapter]["ignored"] += 1
            # Mark as ignored in the original data structure too
            fls_ids[fls_id]["ignored"] = True
        else:
            fls_ids[fls_id]["ignored"] = False

            # Count coverage if not ignored
            if metadata.get("covered", False):
                covered_ids += 1
                chapters[chapter]["covered"] += 1

    # Calculate coverage percentages
    effective_total = total_ids - ignored_ids
    overall_coverage = (
        (covered_ids / effective_total * 100) if effective_total > 0 else 0
    )

    # Calculate chapter coverage
    chapter_coverage = {}
    for chapter, data in chapters.items():
        effective_chapter_total = data["total"] - data["ignored"]

        if effective_chapter_total == 0:
            # All IDs in this chapter are ignored
            chapter_coverage[chapter] = "IGNORED"
        else:
            chapter_coverage[chapter] = data["covered"] / effective_chapter_total * 100

    # Sort chapters by custom logic to handle mixed types
    def chapter_sort_key(chapter):
        if isinstance(chapter, int):
            return (0, chapter)  # Sort integers first, by their value
        elif isinstance(chapter, str) and chapter.isalpha():
            return (1, chapter)  # Sort letters second, alphabetically
        else:
            return (2, str(chapter))  # Sort anything else last

    sorted_chapters = sorted(chapters.keys(), key=chapter_sort_key)

    # Prepare result
    coverage_data = {
        "total_ids": total_ids,
        "covered_ids": covered_ids,
        "ignored_ids": ignored_ids,
        "effective_total": effective_total,
        "overall_coverage": overall_coverage,
        "chapters": sorted_chapters,
        "chapter_data": chapters,
        "chapter_coverage": chapter_coverage,
    }

    return coverage_data


def log_coverage_report(coverage_data):
    """Log a report of FLS coverage statistics"""
    logger.info("=== FLS Coverage Report ===")
    logger.info(f"Total FLS IDs: {coverage_data['total_ids']}")
    logger.info(f"Covered FLS IDs: {coverage_data['covered_ids']}")
    logger.info(f"Ignored FLS IDs: {coverage_data['ignored_ids']}")
    logger.info(f"Overall coverage: {coverage_data['overall_coverage']:.2f}%")

    logger.info("\nCoverage by chapter:")
    for chapter in coverage_data["chapters"]:
        coverage = coverage_data["chapter_coverage"][chapter]
        if coverage == "IGNORED":
            logger.info(f"  Chapter {chapter}: IGNORED (all IDs are on ignore list)")
        else:
            logger.info(f"  Chapter {chapter}: {coverage:.2f}%")
