import copy
from typing import Any

import pytest

from scripts.fls_audit_issue_lib import reconcile as reconciliation
from scripts.fls_audit_issue_lib import render
from scripts.fls_audit_issue_lib import state as state_model
from scripts.fls_audit_issue_lib.errors import AuditIssueError
from tests.fls_audit_fixtures import report_with_changes, spec_lock
from tests.integration.fls_audit.fake_github import FakeGitHubClient, current_issue


def reconcile(
    client: FakeGitHubClient,
    report: dict,
    *,
    limits: state_model.BodyLimits = state_model.DEFAULT_BODY_LIMITS,
) -> str:
    return reconciliation.reconcile(
        client,
        report,
        "# Report\n",
        spec_lock(),
        "fls-audit",
        "FLS audit:",
        limits=limits,
    )


@pytest.mark.integration
def test_transition_body_overflow_fails_before_comment() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number = next(iter(client.issue_values))
    current_size = len(client.issue_values[number]["body"].encode("utf-8"))
    limits = state_model.BodyLimits(issue_body_bytes=current_size + 100)
    client.mutations.clear()

    with pytest.raises(AuditIssueError, match="Compact issue body"):
        reconcile(client, report_with_changes(live_checksum="x" * 1_000), limits=limits)

    assert client.mutations == []
    assert client.comment_values.get(number, []) == []


@pytest.mark.integration
@pytest.mark.parametrize("invalid_lock", [{}, {"documents": []}, {"documents": {}}])
def test_invalid_spec_lock_fails_before_client_mutation(invalid_lock: dict) -> None:
    client = FakeGitHubClient()
    client.label_exists = False

    with pytest.raises(AuditIssueError, match="documents must be a nonempty list"):
        reconciliation.reconcile(
            client,
            report_with_changes(),
            "# Report\n",
            invalid_lock,
            "fls-audit",
            "FLS audit:",
        )

    assert client.mutations == []


@pytest.mark.integration
def test_create_failure_before_write_is_safe_to_retry() -> None:
    client = FakeGitHubClient()
    client.fail("create", "before")

    with pytest.raises(AuditIssueError, match="create failed before write"):
        reconcile(client, report_with_changes())

    assert client.issue_values == {}
    assert client.sleep_delays == [1, 2, 4, 8]
    reconcile(client, report_with_changes())
    assert len(client.issue_values) == 1


@pytest.mark.integration
def test_create_failure_after_write_recovers_created_issue() -> None:
    client = FakeGitHubClient()
    client.fail("create", "after")
    client.stale_after_write["create"] = 2
    client.read_failures_after_write["create"] = 1

    reconcile(client, report_with_changes())

    assert len(client.issue_values) == 1
    assert [mutation[0] for mutation in client.mutations].count("create") == 1
    assert client.sleep_delays == [1, 2, 4]


@pytest.mark.integration
def test_comment_failure_before_write_is_safe_to_retry() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, _, initial = current_issue(client)
    client.fail("comment", "before")

    with pytest.raises(AuditIssueError, match="comment failed before write"):
        reconcile(client, report_with_changes(live_checksum="live-b"))

    assert client.comment_values.get(number, []) == []
    assert client.sleep_delays == [1, 2, 4, 8]
    _, _, stale = current_issue(client)
    assert stale["sequence"] == initial["sequence"]

    reconcile(client, report_with_changes(live_checksum="live-b"))
    assert len(client.comment_values[number]) == 1


@pytest.mark.integration
def test_ambiguous_comment_polls_through_stale_reads() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, _, _ = current_issue(client)
    client.fail("comment", "after")
    client.stale_after_write["comment"] = 2
    client.read_failures_after_write["comment"] = 1

    reconcile(client, report_with_changes(live_checksum="live-b"))

    assert len(client.comment_values[number]) == 1
    assert client.sleep_delays == [1, 2, 4]


@pytest.mark.integration
@pytest.mark.parametrize("timing", ["before", "after"])
def test_label_failure_is_safe_to_retry(timing: str) -> None:
    client = FakeGitHubClient()
    client.label_exists = False
    client.fail("label", timing)

    with pytest.raises(AuditIssueError, match=f"label failed {timing} write"):
        reconcile(client, report_with_changes())

    assert client.issue_values == {}
    reconcile(client, report_with_changes())
    assert client.label_exists
    assert len(client.issue_values) == 1


@pytest.mark.integration
def test_comment_is_recovered_after_body_patch_failure() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, _, initial = current_issue(client)
    client.fail("body_patch", "before")

    with pytest.raises(AuditIssueError, match="body_patch failed before write"):
        reconcile(client, report_with_changes(live_checksum="live-b"))

    assert len(client.comment_values[number]) == 1
    _, _, stale = current_issue(client)
    assert stale["sequence"] == initial["sequence"] == 0
    client.mutations.clear()

    reconcile(client, report_with_changes(live_checksum="live-b"))

    assert [mutation[0] for mutation in client.mutations] == ["patch"]
    assert len(client.comment_values[number]) == 1
    _, _, recovered = current_issue(client)
    assert recovered["sequence"] == 1


@pytest.mark.integration
def test_body_patch_failure_after_write_is_idempotent_on_retry() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, _, _ = current_issue(client)
    client.fail("body_patch", "after")

    with pytest.raises(AuditIssueError, match="body_patch failed after write"):
        reconcile(client, report_with_changes(live_checksum="live-b"))

    assert len(client.comment_values[number]) == 1
    _, _, written = current_issue(client)
    assert written["sequence"] == 1
    client.mutations.clear()

    reconcile(client, report_with_changes(live_checksum="live-b"))

    assert client.mutations == []
    assert len(client.comment_values[number]) == 1


@pytest.mark.integration
def test_untrusted_comment_marker_cannot_advance_state() -> None:
    client = FakeGitHubClient()
    first = report_with_changes()
    second = report_with_changes(live_checksum="live-b")
    reconcile(client, first)
    number, _, state = current_issue(client)
    target = state_model.make_applied(second, "# Report\n", state_model.canonical_items(second))
    value = state_model.batch_id(
        state["campaign"], 1, state["applied"]["semantic_digest"], target["semantic_digest"]
    )
    client.comment_values[number] = [
        {
            "id": 1,
            "body": state_model.batch_marker(
                state["campaign"], 1, value, target, state["applied"]["semantic_digest"]
            ),
            "user": {"login": "contributor", "id": 7, "type": "User"},
        }
    ]
    client.mutations.clear()

    reconcile(client, second)

    assert [mutation[0] for mutation in client.mutations] == ["comment", "patch"]
    assert len(client.comment_values[number]) == 2
    _, _, updated = current_issue(client)
    assert updated["sequence"] == 1


@pytest.mark.integration
def test_untrusted_issue_marker_cannot_claim_campaign() -> None:
    client = FakeGitHubClient()
    report = report_with_changes()
    current = state_model.make_applied(report, "# Report\n", state_model.canonical_items(report))
    state = state_model.make_state(state_model.campaign_id(spec_lock()), 0, current)
    client.issue_values[100] = {
        "number": 100,
        "title": reconciliation.expected_title("FLS audit:", state["campaign"]),
        "body": render.managed_body("", report, "# Report\n", state, ""),
        "labels": [{"name": "fls-audit"}],
        "state": "open",
        "user": {"login": "contributor", "id": 7, "type": "User"},
    }

    reconcile(client, report)

    assert set(client.issue_values) == {100, 2000}
    assert client.issue_values[100]["body"] == render.managed_body("", report, "# Report\n", state, "")


@pytest.mark.integration
@pytest.mark.parametrize("timing", ["before", "after"])
def test_identity_patch_failure_is_safe_to_retry(timing: str) -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, issue, _ = current_issue(client)
    issue["title"] = "damaged title"
    issue["labels"] = []
    client.fail("identity_patch", timing)

    with pytest.raises(AuditIssueError, match=f"identity_patch failed {timing} write"):
        reconcile(client, report_with_changes())

    reconcile(client, report_with_changes())
    assert client.issue_values[number]["title"].startswith("FLS audit: spec.lock drift")
    assert client.issue_values[number]["labels"] == [{"name": "fls-audit"}]


@pytest.mark.integration
@pytest.mark.parametrize("timing", ["before", "after"])
def test_close_failure_is_idempotent_on_retry(timing: str) -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, _, _ = current_issue(client)
    clean = report_with_changes()
    clean["changes"] = {"added": [], "removed": [], "changed": []}
    clean["affected_guidelines"] = {}
    clean["summary"] = dict.fromkeys(clean["summary"], 0)
    clean["text"] = {"added": {}, "removed": {}, "content_diffs": []}
    client.fail("state_patch", timing)

    with pytest.raises(AuditIssueError, match=f"state_patch failed {timing} write"):
        reconcile(client, clean)

    assert len(client.comment_values[number]) == 1
    client.mutations.clear()
    reconcile(client, clean)
    assert len(client.comment_values[number]) == 1
    assert client.issue_values[number]["state"] == "closed"
    assert [mutation[0] for mutation in client.mutations] == (["patch"] if timing == "before" else [])


@pytest.mark.integration
def test_concurrent_state_change_is_not_overwritten() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, _, _ = current_issue(client)

    def change_state(issue: dict[str, Any]) -> None:
        state = state_model.parse_state(issue["body"])
        assert state is not None
        state["applied"]["body_digest"] = f"sha256:{'f' * 64}"
        issue["body"] = state_model.STATE_RE.sub(state_model.state_marker(state), issue["body"])

    client.issue_read_hook = change_state

    with pytest.raises(AuditIssueError, match="changed concurrently"):
        reconcile(client, report_with_changes(live_checksum="live-b"))

    state = state_model.parse_state(client.issue_values[number]["body"])
    assert state is not None and state["sequence"] == 0


@pytest.mark.integration
@pytest.mark.parametrize("timing", ["before", "after"])
def test_reopen_failure_is_safe_to_retry(timing: str) -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, issue, _ = current_issue(client)
    issue["state"] = "closed"
    client.fail("state_patch", timing)

    with pytest.raises(AuditIssueError, match=f"state_patch failed {timing} write"):
        reconcile(client, report_with_changes(live_checksum="live-b"))

    assert client.comment_values.get(number, []) == []
    reconcile(client, report_with_changes(live_checksum="live-b"))
    assert client.issue_values[number]["state"] == "open"
    assert len(client.comment_values[number]) == 1


@pytest.mark.integration
def test_superseded_campaign_close_failure_does_not_duplicate_comment() -> None:
    client = FakeGitHubClient()
    report = report_with_changes()
    reconcile(client, report)
    old_number, _, _ = current_issue(client)
    new_lock = {"documents": [{"link": "two.html", "sections": [{"id": "fls_two"}]}]}
    client.fail("state_patch", "before")

    with pytest.raises(AuditIssueError, match="state_patch failed before write"):
        reconciliation.reconcile(client, report, "# Report\n", new_lock, "fls-audit", "FLS audit:")

    assert len(client.comment_values[old_number]) == 1
    reconciliation.reconcile(client, report, "# Report\n", new_lock, "fls-audit", "FLS audit:")
    assert len(client.comment_values[old_number]) == 1
    assert client.issue_values[old_number]["state"] == "closed"


@pytest.mark.integration
def test_duplicate_bot_batch_marker_fails_without_mutation() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    reconcile(client, report_with_changes(live_checksum="live-b"))
    number, _, _ = current_issue(client)
    duplicate = copy.deepcopy(client.comment_values[number][0])
    duplicate["id"] = 999
    client.comment_values[number].append(duplicate)
    client.mutations.clear()

    with pytest.raises(AuditIssueError, match="duplicate bot batch markers"):
        reconcile(client, report_with_changes(live_checksum="live-b"))

    assert client.mutations == []


@pytest.mark.integration
def test_runtime_verification_detects_deleted_transition_comment() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    reconcile(client, report_with_changes(live_checksum="live-b"))
    number, _, _ = current_issue(client)
    client.comment_values[number] = []
    with pytest.raises(AuditIssueError, match="comment history does not match"):
        reconcile(client, report_with_changes(live_checksum="live-b"))

    assert client.sleep_delays == [1, 2]


@pytest.mark.integration
def test_duplicate_campaign_issues_fail_without_mutation() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, issue, _ = current_issue(client)
    duplicate = copy.deepcopy(issue)
    duplicate["number"] = number + 1
    client.issue_values[number + 1] = duplicate
    client.mutations.clear()

    with pytest.raises(AuditIssueError, match="Multiple FLS audit issues claim campaign"):
        reconcile(client, report_with_changes())

    assert client.mutations == []
