import hashlib
import json
import re
from typing import Any, NamedTuple

from .errors import AuditIssueError


class BodyLimits(NamedTuple):
    issue_body_bytes: int = 60_000
    comment_body_bytes: int = 60_000


DEFAULT_BODY_LIMITS = BodyLimits()

MANAGED_START = "<!-- fls-audit:managed:start -->"
MANAGED_END = "<!-- fls-audit:managed:end -->"
STATE_RE = re.compile(r"<!-- fls-audit:state:v1\n(?P<state>\{.*?\})\n-->", re.DOTALL)
BATCH_RE = re.compile(r"<!-- fls-audit:batch:v1\n(?P<marker>\{.*?\})\n-->", re.DOTALL)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

BODY_DIGEST_FIELDS = (
    "affected_guidelines",
    "changes",
    "header_changes",
    "new_paragraph_assessments",
    "relevance",
    "section_reorders",
    "summary",
    "text",
)


def compact_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: object) -> str:
    return f"sha256:{hashlib.sha256(compact_json(value).encode()).hexdigest()}"


def check_size(value: str, limit: int, description: str) -> None:
    size = len(value.encode("utf-8"))
    if size > limit:
        raise AuditIssueError(f"{description} is {size} bytes; limit is {limit} bytes")


def campaign_id(spec_lock: dict[str, Any]) -> str:
    documents = spec_lock.get("documents")
    if not isinstance(documents, list) or not documents:
        raise AuditIssueError("spec.lock documents must be a nonempty list")
    return sha256_json(documents)


def paragraph_side(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"checksum": "", "section": ""}
    return {
        "checksum": str(value.get("checksum", "")),
        "section": str(value.get("section_id", "")),
    }


def canonical_items(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    changes = report.get("changes", {})
    if not isinstance(changes, dict):
        raise AuditIssueError("Audit report changes must be an object")

    for kind in ("added", "removed", "changed"):
        entries = changes.get(kind, [])
        if not isinstance(entries, list):
            raise AuditIssueError(f"Audit report changes.{kind} must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("fls_id"):
                raise AuditIssueError(f"Audit report changes.{kind} contains an invalid entry")
            fls_id = str(entry["fls_id"])
            key = f"paragraph:{fls_id}"
            if key in items:
                raise AuditIssueError(f"Audit report contains duplicate paragraph {fls_id}")
            item: dict[str, Any] = {
                "kind": kind,
                "locked": paragraph_side(entry.get("locked")),
                "live": paragraph_side(entry.get("live")),
            }
            if kind == "changed":
                item["content_changed"] = bool(entry.get("content_changed"))
                item["section_changed"] = bool(entry.get("section_changed"))
            items[key] = item

    for report_key, prefix in (("header_changes", "header"), ("section_reorders", "reorder")):
        entries = report.get(report_key, [])
        if not isinstance(entries, list):
            raise AuditIssueError(f"Audit report {report_key} must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise AuditIssueError(f"Audit report {report_key} contains an invalid entry")
            section_id = entry.get("section_id") or entry.get("fls_id")
            if not section_id:
                raise AuditIssueError(f"Audit report {report_key} entry has no section identity")
            key = f"{prefix}:{section_id}"
            if key in items:
                raise AuditIssueError(f"Audit report contains duplicate item {key}")
            items[key] = {"kind": prefix, "value": entry}

    return dict(sorted(items.items()))


def normalized_report_markdown(report_md: str) -> str:
    volatile_prefixes = ("- Generated: ", "- Spec lock: ")
    return "\n".join(line for line in report_md.rstrip().splitlines() if not line.startswith(volatile_prefixes))


def report_body_digest(report: dict[str, Any], report_md: str) -> str:
    return sha256_json(
        {
            "fields": {key: report.get(key) for key in BODY_DIGEST_FIELDS},
            "markdown": normalized_report_markdown(report_md),
        }
    )


def report_commit(report: dict[str, Any], key: str) -> str:
    metadata = report.get("metadata", {})
    if not isinstance(metadata, dict):
        return ""
    value = metadata.get(key)
    return str(value) if value else ""


def make_applied(report: dict[str, Any], report_md: str, items: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "semantic_digest": sha256_json(items),
        "body_digest": report_body_digest(report, report_md),
        "current_commit": report_commit(report, "current_commit"),
        "items": items,
    }


def validate_applied(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"semantic_digest", "body_digest", "current_commit", "items"}:
        raise AuditIssueError("FLS audit applied state has an invalid schema")
    items = value.get("items")
    if not isinstance(items, dict) or not all(
        isinstance(key, str) and isinstance(item, dict) for key, item in items.items()
    ):
        raise AuditIssueError("FLS audit applied state has no item map")
    if not all(
        isinstance(value.get(key), str) and DIGEST_RE.fullmatch(value[key])
        for key in ("semantic_digest", "body_digest")
    ):
        raise AuditIssueError("FLS audit applied state has invalid digests")
    if value["semantic_digest"] != sha256_json(items):
        raise AuditIssueError("FLS audit applied state digest does not match its item map")
    commit = value.get("current_commit")
    if not isinstance(commit, str) or (commit and not COMMIT_RE.fullmatch(commit)):
        raise AuditIssueError("FLS audit applied state has an invalid current commit")
    return value


def make_state(
    campaign: str,
    sequence: int,
    applied: dict[str, Any],
    origin_semantic_digest: str | None = None,
) -> dict[str, Any]:
    applied = validate_applied(applied)
    origin = origin_semantic_digest or applied["semantic_digest"]
    return {
        "version": 1,
        "campaign": campaign,
        "sequence": sequence,
        "origin_semantic_digest": origin,
        "applied": applied,
    }


def validate_state(value: object) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "campaign", "sequence", "origin_semantic_digest", "applied"}
        or value.get("version") != 1
    ):
        raise AuditIssueError("Unsupported or malformed FLS audit issue state")
    sequence = value.get("sequence")
    if not isinstance(value.get("campaign"), str) or not DIGEST_RE.fullmatch(value["campaign"]):
        raise AuditIssueError("FLS audit issue state has invalid campaign or sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise AuditIssueError("FLS audit issue state has invalid campaign or sequence")
    origin = value.get("origin_semantic_digest")
    if not isinstance(origin, str) or not DIGEST_RE.fullmatch(origin):
        raise AuditIssueError("FLS audit issue state has an invalid origin semantic digest")
    applied = validate_applied(value.get("applied"))
    if sequence == 0 and origin != applied["semantic_digest"]:
        raise AuditIssueError("FLS audit issue origin does not match its sequence-zero state")
    return value


def managed_span(body: str) -> tuple[int, int] | None:
    start_count = body.count(MANAGED_START)
    end_count = body.count(MANAGED_END)
    if start_count == 0 and end_count == 0:
        return None
    if start_count != 1 or end_count != 1:
        raise AuditIssueError("FLS audit issue managed region is missing or ambiguous")
    start = body.index(MANAGED_START)
    end = body.index(MANAGED_END)
    if end < start:
        raise AuditIssueError("FLS audit issue managed region boundaries are reversed")
    return start, end + len(MANAGED_END)


def parse_state(body: str, limits: BodyLimits = DEFAULT_BODY_LIMITS) -> dict[str, Any] | None:
    check_size(body, limits.issue_body_bytes, "Existing issue body")
    matches = list(STATE_RE.finditer(body))
    if not matches:
        if "fls-audit:state:" in body:
            raise AuditIssueError("FLS audit issue contains an unsupported state marker")
        if managed_span(body) is not None:
            raise AuditIssueError("FLS audit issue managed region has no state marker")
        return None
    if len(matches) != 1:
        raise AuditIssueError("FLS audit issue contains multiple state markers")
    span = managed_span(body)
    if span is None or not (span[0] < matches[0].start() and matches[0].end() < span[1]):
        raise AuditIssueError("FLS audit issue state marker is outside its managed region")
    try:
        return validate_state(json.loads(matches[0].group("state")))
    except json.JSONDecodeError as error:
        raise AuditIssueError("FLS audit issue state is not valid JSON") from error


def state_marker(state: dict[str, Any]) -> str:
    return f"<!-- fls-audit:state:v1\n{compact_json(state)}\n-->"


def diff_items(
    previous: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    new = sorted(current.keys() - previous.keys())
    updated = sorted(key for key in current.keys() & previous.keys() if current[key] != previous[key])
    resolved = sorted(previous.keys() - current.keys())
    return new, updated, resolved


def batch_id(campaign: str, sequence: int, previous_digest: str, target_digest: str) -> str:
    return sha256_json(
        {"campaign": campaign, "sequence": sequence, "previous": previous_digest, "target": target_digest}
    )


def batch_marker(
    campaign: str,
    sequence: int,
    value: str,
    applied: dict[str, Any] | None = None,
    previous_semantic_digest: str | None = None,
) -> str:
    marker: dict[str, Any] = {"batch_id": value, "campaign": campaign, "sequence": sequence}
    if applied is not None:
        if previous_semantic_digest is None:
            raise AuditIssueError("FLS audit transition marker has no previous semantic digest")
        marker["previous_semantic_digest"] = previous_semantic_digest
        marker["applied"] = applied
    return f"<!-- fls-audit:batch:v1\n{compact_json(marker)}\n-->"


def parse_batch_marker(body: str, limits: BodyLimits = DEFAULT_BODY_LIMITS) -> dict[str, Any] | None:
    check_size(body, limits.comment_body_bytes, "Existing audit comment")
    matches = list(BATCH_RE.finditer(body))
    if not matches:
        if "fls-audit:batch:" in body:
            raise AuditIssueError("FLS audit comment contains an unsupported batch marker")
        return None
    if len(matches) != 1:
        raise AuditIssueError("FLS audit comment contains multiple batch markers")
    try:
        marker = json.loads(matches[0].group("marker"))
    except json.JSONDecodeError as error:
        raise AuditIssueError("FLS audit batch marker is not valid JSON") from error
    base = {"batch_id", "campaign", "sequence"}
    if not isinstance(marker, dict) or not base <= set(marker):
        raise AuditIssueError("FLS audit batch marker has an invalid schema")
    expected = base | ({"previous_semantic_digest", "applied"} if "applied" in marker else set())
    if set(marker) != expected:
        raise AuditIssueError("FLS audit batch marker has an invalid schema")
    sequence = marker.get("sequence")
    if not isinstance(marker.get("batch_id"), str) or not DIGEST_RE.fullmatch(marker["batch_id"]):
        raise AuditIssueError("FLS audit batch marker has an invalid batch ID")
    if not isinstance(marker.get("campaign"), str) or not marker["campaign"]:
        raise AuditIssueError("FLS audit batch marker has an invalid campaign")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise AuditIssueError("FLS audit batch marker has an invalid sequence")
    if "applied" in marker:
        previous = marker.get("previous_semantic_digest")
        if not isinstance(previous, str) or not DIGEST_RE.fullmatch(previous):
            raise AuditIssueError("FLS audit batch marker has an invalid previous semantic digest")
        validate_applied(marker["applied"])
    return marker
