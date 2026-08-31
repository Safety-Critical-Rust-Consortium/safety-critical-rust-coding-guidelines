import copy
from pathlib import Path

import pytest

from scripts.fls_audit_issue_lib import reconcile, state
from scripts.fls_audit_issue_lib.errors import AuditIssueError
from tests.fls_audit_fixtures import report_with_changes, spec_lock

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "fls_audit" / "golden"


def golden(name: str) -> str:
    return (GOLDEN_DIR / name).read_text(encoding="utf-8").removesuffix("\n")


def test_campaign_ignores_metadata_and_json_formatting() -> None:
    first = spec_lock()
    second = copy.deepcopy(first)
    second["metadata"] = {"ignored": False, "new": "value"}

    assert state.campaign_id(first) == state.campaign_id(second)


def test_canonical_items_and_net_delta() -> None:
    previous_report = report_with_changes(live_checksum="live-a")
    current_report = report_with_changes(live_checksum="live-b")
    current_report["changes"]["removed"] = [
        {
            "fls_id": "fls_removed",
            "locked": {"checksum": "gone", "section_id": "3:1"},
        }
    ]
    previous = state.canonical_items(previous_report)
    current = state.canonical_items(current_report)

    new, updated, resolved = state.diff_items(previous, current)

    assert new == ["paragraph:fls_removed"]
    assert updated == ["paragraph:fls_added"]
    assert resolved == []


def test_body_digest_ignores_volatile_metadata_but_tracks_impact() -> None:
    first = report_with_changes()
    second = copy.deepcopy(first)
    second["metadata"]["generated_at"] = "later"
    second["metadata"]["spec_lock"] = "/different/path"

    markdown = "# Report\n\n- Generated: first\n- Spec lock: `/first/path`\n\nStable\n"
    other_markdown = "# Report\n\n- Generated: second\n- Spec lock: `/other/path`\n\nStable\n"
    assert state.report_body_digest(first, markdown) == state.report_body_digest(second, other_markdown)

    second["affected_guidelines"] = {}
    assert state.report_body_digest(first, markdown) != state.report_body_digest(second, other_markdown)
    assert state.report_body_digest(first, markdown) != state.report_body_digest(first, f"{markdown}Changed\n")

    second["metadata"] = []
    assert state.report_commit(second, "current_commit") == ""


def test_state_marker_matches_golden() -> None:
    report = report_with_changes()
    applied = state.make_applied(report, "# Current report\n", state.canonical_items(report))
    issue_state = state.make_state(state.campaign_id(spec_lock()), 0, applied)

    assert state.state_marker(issue_state) == golden("state-marker.md")


def test_state_requires_consistent_schema_and_managed_region() -> None:
    report = report_with_changes()
    applied = state.make_applied(report, "# Report\n", state.canonical_items(report))
    issue_state = state.make_state(state.campaign_id(spec_lock()), 0, applied)

    damaged = copy.deepcopy(issue_state)
    damaged["sequence"] = True
    with pytest.raises(AuditIssueError, match="invalid campaign or sequence"):
        state.validate_state(damaged)

    damaged = copy.deepcopy(issue_state)
    damaged["applied"]["items"] = {}
    with pytest.raises(AuditIssueError, match="does not match"):
        state.validate_state(damaged)

    damaged = copy.deepcopy(issue_state)
    damaged["origin_semantic_digest"] = "sha256:" + "0" * 64
    with pytest.raises(AuditIssueError, match="sequence-zero state"):
        state.validate_state(damaged)

    with pytest.raises(AuditIssueError, match="outside its managed region"):
        state.parse_state(state.state_marker(issue_state))

    reversed_region = f"{state.MANAGED_END}\n{state.state_marker(issue_state)}\n{state.MANAGED_START}"
    with pytest.raises(AuditIssueError, match="boundaries are reversed"):
        state.parse_state(reversed_region)


def test_canonical_items_rejects_malformed_report_shapes() -> None:
    cases: list[tuple[dict, str]] = []

    report = report_with_changes()
    report["changes"] = []
    cases.append((report, "changes must be an object"))

    report = report_with_changes()
    report["changes"]["added"] = {}
    cases.append((report, "changes.added must be a list"))

    report = report_with_changes()
    report["changes"]["removed"] = [None]
    cases.append((report, "changes.removed contains an invalid entry"))

    report = report_with_changes()
    report["changes"]["removed"] = [copy.deepcopy(report["changes"]["added"][0])]
    cases.append((report, "duplicate paragraph fls_added"))

    report = report_with_changes()
    report["header_changes"] = {}
    cases.append((report, "header_changes must be a list"))

    report = report_with_changes()
    report["header_changes"] = [None]
    cases.append((report, "header_changes contains an invalid entry"))

    report = report_with_changes()
    report["header_changes"] = [{}]
    cases.append((report, "header_changes entry has no section identity"))

    report = report_with_changes()
    structural = {"section_id": "fls_duplicate"}
    report["header_changes"] = [structural, copy.deepcopy(structural)]
    cases.append((report, "duplicate item header:fls_duplicate"))

    for invalid_report, message in cases:
        with pytest.raises(AuditIssueError, match=message):
            state.canonical_items(invalid_report)


def test_applied_state_validation_guards() -> None:
    report = report_with_changes()
    applied = state.make_applied(report, "# Report\n", state.canonical_items(report))
    cases: list[tuple[object, str]] = [
        (None, "invalid schema"),
        ({**applied, "extra": True}, "invalid schema"),
        ({**applied, "items": []}, "no item map"),
        ({**applied, "items": {"paragraph:x": "invalid"}}, "no item map"),
        ({**applied, "semantic_digest": "invalid"}, "invalid digests"),
        ({**applied, "body_digest": "invalid"}, "invalid digests"),
        ({**applied, "current_commit": "not-a-commit"}, "invalid current commit"),
    ]

    for invalid, message in cases:
        with pytest.raises(AuditIssueError, match=message):
            state.validate_applied(invalid)


def test_issue_state_validation_guards() -> None:
    report = report_with_changes()
    applied = state.make_applied(report, "# Report\n", state.canonical_items(report))
    issue_state = state.make_state(state.campaign_id(spec_lock()), 0, applied)
    cases: list[tuple[object, str]] = [
        (None, "Unsupported or malformed"),
        ({**issue_state, "version": 2}, "Unsupported or malformed"),
        ({**issue_state, "campaign": "invalid"}, "invalid campaign or sequence"),
        ({**issue_state, "sequence": -1}, "invalid campaign or sequence"),
        ({**issue_state, "origin_semantic_digest": "invalid"}, "invalid origin semantic digest"),
        ({**issue_state, "applied": None}, "applied state has an invalid schema"),
    ]

    for invalid, message in cases:
        with pytest.raises(AuditIssueError, match=message):
            state.validate_state(invalid)


def test_state_marker_parsing_guards() -> None:
    report = report_with_changes()
    applied = state.make_applied(report, "# Report\n", state.canonical_items(report))
    issue_state = state.make_state(state.campaign_id(spec_lock()), 0, applied)
    marker = state.state_marker(issue_state)
    managed = f"{state.MANAGED_START}\n{marker}\n{state.MANAGED_END}"

    assert state.parse_state(managed) == issue_state
    assert state.parse_state("ordinary issue body") is None

    with pytest.raises(AuditIssueError, match="unsupported state marker"):
        state.parse_state("<!-- fls-audit:state:v2\n{}\n-->")
    with pytest.raises(AuditIssueError, match="managed region has no state marker"):
        state.parse_state(f"{state.MANAGED_START}\nNo marker\n{state.MANAGED_END}")
    with pytest.raises(AuditIssueError, match="missing or ambiguous"):
        state.parse_state(f"{state.MANAGED_START}\n{state.MANAGED_START}\n{state.MANAGED_END}")
    with pytest.raises(AuditIssueError, match="multiple state markers"):
        state.parse_state(f"{state.MANAGED_START}\n{marker}\n{marker}\n{state.MANAGED_END}")
    with pytest.raises(AuditIssueError, match="not valid JSON"):
        state.parse_state(f"{state.MANAGED_START}\n<!-- fls-audit:state:v1\n{{bad}}\n-->\n{state.MANAGED_END}")


def test_batch_marker_validation_guards() -> None:
    report = report_with_changes()
    applied = state.make_applied(report, "# Report\n", state.canonical_items(report))
    campaign = state.campaign_id(spec_lock())
    digest = state.batch_id(campaign, 1, applied["semantic_digest"], applied["semantic_digest"])

    with pytest.raises(AuditIssueError, match="no previous semantic digest"):
        state.batch_marker(campaign, 1, digest, applied)

    valid = state.batch_marker(campaign, 1, digest, applied, applied["semantic_digest"])
    assert state.parse_batch_marker(valid) is not None
    assert state.parse_batch_marker("ordinary comment") is None

    with pytest.raises(AuditIssueError, match="unsupported batch marker"):
        state.parse_batch_marker("<!-- fls-audit:batch:v2\n{}\n-->")
    with pytest.raises(AuditIssueError, match="multiple batch markers"):
        state.parse_batch_marker(f"{valid}\n{valid}")
    with pytest.raises(AuditIssueError, match="not valid JSON"):
        state.parse_batch_marker("<!-- fls-audit:batch:v1\n{bad}\n-->")

    base = {"batch_id": digest, "campaign": campaign, "sequence": 1}
    cases: list[tuple[object, str]] = [
        ({"batch_id": digest}, "invalid schema"),
        ({**base, "extra": True}, "invalid schema"),
        ({**base, "batch_id": "invalid"}, "invalid batch ID"),
        ({**base, "campaign": ""}, "invalid campaign"),
        ({**base, "sequence": True}, "invalid sequence"),
        ({**base, "applied": applied}, "invalid schema"),
        (
            {**base, "applied": applied, "previous_semantic_digest": "invalid"},
            "invalid previous semantic digest",
        ),
        (
            {**base, "applied": None, "previous_semantic_digest": applied["semantic_digest"]},
            "applied state has an invalid schema",
        ),
    ]
    for marker_value, message in cases:
        body = f"<!-- fls-audit:batch:v1\n{state.compact_json(marker_value)}\n-->"
        with pytest.raises(AuditIssueError, match=message):
            state.parse_batch_marker(body)


def test_comment_recovery_rejects_sequence_gap() -> None:
    report = report_with_changes()
    current_report = report_with_changes(live_checksum="new")
    previous = state.make_applied(report, "# Report\n", state.canonical_items(report))
    current = state.make_applied(current_report, "# Report\n", state.canonical_items(current_report))
    campaign = state.campaign_id(spec_lock())
    issue_state = state.make_state(campaign, 0, previous)
    value = state.batch_id(campaign, 2, previous["semantic_digest"], current["semantic_digest"])
    comment = {
        "body": state.batch_marker(campaign, 2, value, current, previous["semantic_digest"]),
        "user": {
            "login": reconcile.ACTIONS_BOT_LOGIN,
            "id": reconcile.ACTIONS_BOT_ID,
            "type": "Bot",
        },
    }

    with pytest.raises(AuditIssueError, match="sequence jumps"):
        reconcile.recover_from_comments(issue_state, [comment])


def test_first_transition_is_grounded_in_campaign_origin() -> None:
    report = report_with_changes()
    current_report = report_with_changes(live_checksum="new")
    origin = state.make_applied(report, "# Report\n", state.canonical_items(report))
    current = state.make_applied(current_report, "# Report\n", state.canonical_items(current_report))
    campaign = state.campaign_id(spec_lock())
    issue_state = state.make_state(campaign, 1, current, origin["semantic_digest"])
    wrong_previous = "sha256:" + "0" * 64
    value = state.batch_id(campaign, 1, wrong_previous, current["semantic_digest"])
    comment = {
        "body": state.batch_marker(campaign, 1, value, current, wrong_previous),
        "user": {
            "login": reconcile.ACTIONS_BOT_LOGIN,
            "id": reconcile.ACTIONS_BOT_ID,
            "type": "Bot",
        },
    }

    with pytest.raises(AuditIssueError, match="invalid historical batch chain"):
        reconcile.verify_comment_history(issue_state, [comment])
