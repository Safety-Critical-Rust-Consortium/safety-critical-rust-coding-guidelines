from typing import Any

from .errors import AuditIssueError
from .state import (
    DEFAULT_BODY_LIMITS,
    MANAGED_END,
    MANAGED_START,
    STATE_RE,
    BodyLimits,
    batch_marker,
    check_size,
    diff_items,
    managed_span,
    state_marker,
)


def replace_managed(body: str, managed: str) -> str:
    span = managed_span(body)
    if span is None:
        return f"{body.rstrip()}\n\n{managed}" if body else managed
    return f"{body[: span[0]]}{managed}{body[span[1] :]}"


def comparable_managed_body(body: str) -> str:
    span = managed_span(body)
    if span is None:
        raise AuditIssueError("FLS audit issue has no managed region")
    managed = STATE_RE.sub("<!-- fls-audit:state -->", body[span[0] : span[1]])
    volatile_prefixes = (
        "- Generated at: ",
        "- Workflow run: ",
        "- Generated: ",
        "- Spec lock: ",
        "Complete workflow artifact: ",
    )
    return "\n".join(line for line in managed.splitlines() if not line.startswith(volatile_prefixes))


def build_instructions(report: dict[str, Any], workflow_url: str) -> str:
    lines = [
        "## What to do",
        "- Review the current cumulative report below.",
        "- If no guideline updates are required, comment `@guidelines-bot /accept-no-fls-changes` (triage+ only).",
        "- If guideline updates are required, open a synchronization PR and include `Closes #<this issue>`.",
        "- See `docs/fls-audit.md` for the audit workflow.",
        "",
        "## Current audit",
    ]
    generated_at = report.get("metadata", {}).get("generated_at")
    if generated_at:
        lines.append(f"- Generated at: `{generated_at}`")
    if workflow_url:
        lines.append(f"- Workflow run: {workflow_url}")
    lines.extend(["", "---", ""])
    return "\n".join(lines)


def item_summary(key: str, item: dict[str, Any]) -> str:
    kind = str(item.get("kind", "changed"))
    if not key.startswith("paragraph:"):
        return f"`{key}`: {kind}"
    fls_id = key.removeprefix("paragraph:")
    locked = item.get("locked", {})
    live = item.get("live", {})
    locked_section = str(locked.get("section", "")) if isinstance(locked, dict) else ""
    live_section = str(live.get("section", "")) if isinstance(live, dict) else ""
    sections = f"; section `{locked_section or '-'} -> {live_section or '-'}`" if locked_section or live_section else ""
    return f"`{fls_id}`: {kind}{sections}"


def compact_report(report: dict[str, Any], items: dict[str, dict[str, Any]], workflow_url: str) -> str:
    lines = [
        "# FLS Spec Lock Audit Report",
        "",
        "The complete report exceeded the issue body budget. Every active drift item is listed below.",
        "",
        "## Active drift",
    ]
    lines.extend(f"- {item_summary(key, item)}" for key, item in items.items())
    if not items:
        lines.append("- None")
    affected = report.get("affected_guidelines", {})
    lines.extend(["", "## Affected guidelines"])
    if isinstance(affected, dict) and affected:
        for guideline_id, value in sorted(affected.items()):
            title = value.get("title", "Untitled") if isinstance(value, dict) else "Untitled"
            lines.append(f"- `{guideline_id}`: {title}")
    else:
        lines.append("- None")
    if workflow_url:
        lines.extend(["", f"Complete workflow artifact: {workflow_url}"])
    return "\n".join(lines)


def managed_body(
    existing_body: str,
    report: dict[str, Any],
    report_md: str,
    state: dict[str, Any],
    workflow_url: str,
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> str:
    instructions = build_instructions(report, workflow_url)
    managed = f"{MANAGED_START}\n{instructions}{report_md.rstrip()}\n\n{state_marker(state)}\n{MANAGED_END}"
    candidate = replace_managed(existing_body, managed)
    if len(candidate.encode("utf-8")) <= limits.issue_body_bytes:
        return candidate
    compact = compact_report(report, state["applied"]["items"], workflow_url)
    managed = f"{MANAGED_START}\n{instructions}{compact}\n\n{state_marker(state)}\n{MANAGED_END}"
    candidate = replace_managed(existing_body, managed)
    check_size(candidate, limits.issue_body_bytes, "Compact issue body")
    return candidate


def affected_guidelines(report: dict[str, Any]) -> list[str]:
    affected = report.get("affected_guidelines", {})
    if not isinstance(affected, dict) or not affected:
        return ["- None"]
    return [
        f"- `{guideline_id}`: {value.get('title', 'Untitled') if isinstance(value, dict) else 'Untitled'}"
        for guideline_id, value in sorted(affected.items())
    ]


def text_diffs(report: dict[str, Any], fls_ids: set[str]) -> list[str]:
    text = report.get("text", {})
    entries = text.get("content_diffs", []) if isinstance(text, dict) else []
    lines: list[str] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or str(entry.get("fls_id")) not in fls_ids:
            continue
        diff = entry.get("diff", [])
        if not isinstance(diff, list) or not diff:
            continue
        lines.extend(
            [
                "",
                f"<details><summary>{entry['fls_id']} current lock-to-live text</summary>",
                "",
                "```diff",
                *(str(line) for line in diff),
                "```",
                "",
                "</details>",
            ]
        )
    return lines


def transition_comment(
    report: dict[str, Any],
    previous: dict[str, Any],
    current: dict[str, Any],
    campaign: str,
    sequence: int,
    value: str,
    workflow_url: str,
    *,
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
    include_diffs: bool = True,
) -> str:
    previous_items = previous["items"]
    current_items = current["items"]
    new, updated, resolved = diff_items(previous_items, current_items)
    lines = [
        "## FLS drift update",
        "",
        "Net changes since the previous successfully applied bot state:",
        "",
        f"- New: {len(new)}",
        f"- Updated: {len(updated)}",
        f"- Resolved: {len(resolved)}",
    ]
    if previous.get("current_commit"):
        lines.append(f"- Previous FLS commit: `{previous['current_commit']}`")
    if current.get("current_commit"):
        lines.append(f"- Current FLS commit: `{current['current_commit']}`")
    if workflow_url:
        lines.append(f"- Workflow run: {workflow_url}")
    for heading, keys, source in (
        ("New", new, current_items),
        ("Updated", updated, current_items),
        ("Resolved", resolved, previous_items),
    ):
        lines.extend(["", f"### {heading}"])
        lines.extend(f"- {item_summary(key, source[key])}" for key in keys)
        if not keys:
            lines.append("- None")
    if include_diffs:
        ids = {key.removeprefix("paragraph:") for key in new + updated if key.startswith("paragraph:")}
        lines.extend(text_diffs(report, ids))
    lines.extend(["", "### Currently affected guidelines", *affected_guidelines(report), ""])
    lines.append(batch_marker(campaign, sequence, value, current, previous["semantic_digest"]))
    body = "\n".join(lines)
    if len(body.encode("utf-8")) <= limits.comment_body_bytes:
        return body
    if include_diffs:
        return transition_comment(
            report,
            previous,
            current,
            campaign,
            sequence,
            value,
            workflow_url,
            limits=limits,
            include_diffs=False,
        )
    check_size(body, limits.comment_body_bytes, "Compact transition comment")
    return body


def event_comment(campaign: str, value: str, message: str, workflow_url: str) -> str:
    lines = [message]
    if workflow_url:
        lines.extend(["", f"Workflow run: {workflow_url}"])
    lines.extend(["", batch_marker(campaign, 0, value)])
    return "\n".join(lines)
