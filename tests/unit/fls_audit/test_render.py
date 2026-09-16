from pathlib import Path

import pytest

from scripts.fls_audit_issue_lib import render, state
from scripts.fls_audit_issue_lib.errors import AuditIssueError
from tests.fls_audit_fixtures import report_with_changes, spec_lock

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "fls_audit" / "golden"


def golden(name: str) -> str:
    return (GOLDEN_DIR / name).read_text(encoding="utf-8").removesuffix("\n")


def test_managed_body_preserves_human_text() -> None:
    report = report_with_changes()
    applied = state.make_applied(report, "# Current report\n", state.canonical_items(report))
    issue_state = state.make_state(state.campaign_id(spec_lock()), 0, applied)
    original = (
        f"Human preface\n{state.MANAGED_START}\nold\n{state.state_marker(issue_state)}\n"
        f"{state.MANAGED_END}\nHuman footer"
    )

    updated = render.managed_body(
        original,
        report,
        "# Current report\n",
        issue_state,
        "https://example.test/run",
    )

    assert updated.startswith("Human preface\n")
    assert updated.endswith("\nHuman footer")
    assert "# Current report" in updated
    assert state.parse_state(updated) == issue_state


def test_rendering_matches_goldens() -> None:
    report = report_with_changes()
    applied = state.make_applied(report, "# Current report\n", state.canonical_items(report))
    issue_state = state.make_state(state.campaign_id(spec_lock()), 0, applied)
    body = render.managed_body("", report, "# Current report\n", issue_state, "")

    current_report = report_with_changes(live_checksum="newer")
    current_report["changes"]["changed"] = []
    current = state.make_applied(current_report, "# Report\n", state.canonical_items(current_report))
    value = state.batch_id(issue_state["campaign"], 1, applied["semantic_digest"], current["semantic_digest"])
    comment = render.transition_comment(
        current_report,
        applied,
        current,
        issue_state["campaign"],
        1,
        value,
        "",
    )

    assert body == golden("issue-body.md")
    assert comment == golden("transition-comment.md")


def test_transition_comment_lists_all_net_changes() -> None:
    previous_report = report_with_changes()
    current_report = report_with_changes(live_checksum="newer")
    current_report["changes"]["changed"] = []
    previous = state.make_applied(previous_report, "# Report\n", state.canonical_items(previous_report))
    current = state.make_applied(current_report, "# Report\n", state.canonical_items(current_report))
    campaign = state.campaign_id(spec_lock())
    value = state.batch_id(campaign, 1, previous["semantic_digest"], current["semantic_digest"])

    comment = render.transition_comment(current_report, previous, current, campaign, 1, value, "")

    assert "- New: 0" in comment
    assert "- Updated: 1" in comment
    assert "- Resolved: 1" in comment
    assert "`fls_added`" in comment
    assert "`fls_changed`" in comment
    marker = state.parse_batch_marker(comment)
    assert marker is not None and marker["batch_id"] == value
    assert marker["previous_semantic_digest"] == previous["semantic_digest"]


def test_compact_comment_fails_before_silent_truncation() -> None:
    report = report_with_changes()
    previous = state.make_applied(report, "# Report\n", {})
    current = state.make_applied(report, "# Report\n", state.canonical_items(report))
    campaign = state.campaign_id(spec_lock())
    value = state.batch_id(campaign, 1, previous["semantic_digest"], current["semantic_digest"])
    limits = state.BodyLimits(comment_body_bytes=20)

    with pytest.raises(AuditIssueError, match="Compact transition comment"):
        render.transition_comment(report, previous, current, campaign, 1, value, "", limits=limits)


def test_compact_issue_body_ignores_workflow_url_for_idempotence() -> None:
    report = report_with_changes()
    report_md = f"# Report\n{'x' * state.DEFAULT_BODY_LIMITS.issue_body_bytes}\n"
    applied = state.make_applied(report, report_md, state.canonical_items(report))
    issue_state = state.make_state(state.campaign_id(spec_lock()), 0, applied)

    first = render.managed_body("", report, report_md, issue_state, "https://example.test/runs/1")
    second = render.managed_body("", report, report_md, issue_state, "https://example.test/runs/2")

    assert "Complete workflow artifact:" in first
    assert render.comparable_managed_body(first) == render.comparable_managed_body(second)
