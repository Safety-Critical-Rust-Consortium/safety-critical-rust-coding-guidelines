import copy

import pytest

from scripts.fls_audit_issue_lib import reconcile as reconciliation
from scripts.fls_audit_issue_lib import state as state_model
from tests.fls_audit_fixtures import (
    report_with_changes,
    report_with_structural_changes,
    spec_lock,
)
from tests.integration.fls_audit.fake_github import (
    BOT_USER,
    FakeGitHubClient,
    current_issue,
)


def reconcile(client: FakeGitHubClient, report: dict) -> str:
    return reconciliation.reconcile(client, report, "# Report\n", spec_lock(), "fls-audit", "FLS audit:")


@pytest.mark.integration
def test_create_then_identical_run_performs_no_writes() -> None:
    client = FakeGitHubClient()
    report = report_with_changes()

    assert reconcile(client, report) == "Reconciled audit issue #2000."
    assert client.mutations == [("create", 2000)]

    client.mutations.clear()
    assert reconcile(client, report) == "Audit issue #2000 is already current."
    assert client.mutations == []


@pytest.mark.integration
def test_changed_run_posts_one_comment_and_updates_state() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    client.mutations.clear()

    current = report_with_changes(live_checksum="live-b")
    current["metadata"]["current_commit"] = "c" * 40
    assert reconcile(client, current) == "Reconciled audit issue #2000."

    number = next(iter(client.issue_values))
    assert client.mutations == [("comment", 2000), ("patch", 2000)]
    assert len(client.comment_values[number]) == 1
    state = state_model.parse_state(client.issue_values[number]["body"])
    assert state is not None
    assert state["sequence"] == 1


@pytest.mark.integration
def test_structural_drift_flows_through_state_and_transition_rendering() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    client.mutations.clear()

    reconcile(client, report_with_structural_changes())

    number, _, state = current_issue(client)
    assert {"header:fls_section", "reorder:fls_reordered"} <= state["applied"]["items"].keys()
    comment = client.comment_values[number][0]["body"]
    assert "`header:fls_section`: header" in comment
    assert "`reorder:fls_reordered`: reorder" in comment


@pytest.mark.integration
def test_ambiguous_comment_write_is_not_duplicated() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    client.mutations.clear()
    client.fail("comment", "after")

    reconcile(client, report_with_changes(live_checksum="live-b"))

    number = next(iter(client.issue_values))
    assert len(client.comment_values[number]) == 1
    assert [mutation[0] for mutation in client.mutations].count("comment") == 1
    state = state_model.parse_state(client.issue_values[number]["body"])
    assert state is not None and state["sequence"] == 1


@pytest.mark.integration
def test_clean_run_comments_and_closes_campaign() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    client.mutations.clear()
    clean = report_with_changes()
    clean["changes"] = {"added": [], "removed": [], "changed": []}
    clean["affected_guidelines"] = {}
    clean["summary"] = dict.fromkeys(clean["summary"], 0)
    clean["text"] = {"added": {}, "removed": {}, "content_diffs": []}

    assert reconcile(client, clean) == "Reconciled audit issue #2000."

    number = next(iter(client.issue_values))
    assert client.mutations == [("comment", 2000), ("patch", 2000), ("patch", 2000)]
    assert client.issue_values[number]["state"] == "closed"
    assert len(client.comment_values[number]) == 1
    state = state_model.parse_state(client.issue_values[number]["body"])
    assert state is not None and state["applied"]["items"] == {}


@pytest.mark.integration
def test_body_only_change_does_not_comment() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    client.mutations.clear()

    reconcile(client, report_with_changes(affected=False))

    assert [mutation[0] for mutation in client.mutations] == ["patch"]
    number, _, _ = current_issue(client)
    assert client.comment_values.get(number, []) == []


@pytest.mark.integration
def test_damaged_managed_report_is_repaired_without_comment() -> None:
    client = FakeGitHubClient()
    report = report_with_changes()
    reconcile(client, report)
    number, issue, _ = current_issue(client)
    issue["body"] = issue["body"].replace("# Report", "# Damaged report")
    client.mutations.clear()

    reconcile(client, report)

    assert [mutation[0] for mutation in client.mutations] == ["patch"]
    assert "# Damaged report" not in client.issue_values[number]["body"]
    assert client.comment_values.get(number, []) == []


@pytest.mark.integration
def test_human_text_added_during_transition_is_preserved() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, _, _ = current_issue(client)
    client.issue_read_hook = lambda issue: issue.update(body=f"Maintainer note\n\n{issue['body']}")

    reconcile(client, report_with_changes(live_checksum="live-b"))

    assert client.issue_values[number]["body"].startswith("Maintainer note\n\n")


@pytest.mark.integration
def test_runtime_verification_retries_stale_issue_read() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    client.stale_after_write["body_patch"] = 1

    reconcile(client, report_with_changes(live_checksum="live-b"))

    _, _, state = current_issue(client)
    assert state["sequence"] == 1
    assert client.sleep_delays == [1]


@pytest.mark.integration
def test_runtime_verification_retries_issue_and_comment_staleness_independently() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    client.stale_after_write["body_patch"] = 1
    client.stale_after_write["comment"] = 2

    reconcile(client, report_with_changes(live_checksum="live-b"))

    _, _, state = current_issue(client)
    assert state["sequence"] == 1
    assert client.sleep_delays == [1, 1, 2]


@pytest.mark.integration
def test_posted_comment_state_is_recovered_on_next_run() -> None:
    client = FakeGitHubClient()
    first = report_with_changes()
    second = report_with_changes(live_checksum="live-b")
    reconcile(client, first)
    number, issue, state = current_issue(client)
    target = state_model.make_applied(second, "# Report\n", state_model.canonical_items(second))
    value = state_model.batch_id(
        state["campaign"], 1, state["applied"]["semantic_digest"], target["semantic_digest"]
    )
    marker = state_model.batch_marker(
        state["campaign"], 1, value, target, state["applied"]["semantic_digest"]
    )
    client.comment_values[number] = [{"id": 1, "body": marker, "user": copy.deepcopy(BOT_USER)}]
    client.mutations.clear()

    reconcile(client, second)

    _, _, recovered = current_issue(client)
    assert recovered["sequence"] == 1
    assert len(client.comment_values[number]) == 1


@pytest.mark.integration
def test_posted_comment_state_is_used_as_base_for_later_catch_up() -> None:
    client = FakeGitHubClient()
    first = report_with_changes()
    missed = report_with_changes(live_checksum="live-b")
    latest = report_with_changes(live_checksum="live-c")
    reconcile(client, first)
    number, issue, state = current_issue(client)
    missed_target = state_model.make_applied(missed, "# Report\n", state_model.canonical_items(missed))
    value = state_model.batch_id(
        state["campaign"], 1, state["applied"]["semantic_digest"], missed_target["semantic_digest"]
    )
    marker = state_model.batch_marker(
        state["campaign"], 1, value, missed_target, state["applied"]["semantic_digest"]
    )
    client.comment_values[number] = [{"id": 1, "body": marker, "user": copy.deepcopy(BOT_USER)}]
    client.mutations.clear()

    reconcile(client, latest)

    _, _, recovered = current_issue(client)
    latest_target = state_model.make_applied(latest, "# Report\n", state_model.canonical_items(latest))
    assert recovered["applied"]["semantic_digest"] == latest_target["semantic_digest"]
    assert recovered["sequence"] == 2
    assert len(client.comment_values[number]) == 2


@pytest.mark.integration
def test_closed_stale_campaign_reopens() -> None:
    client = FakeGitHubClient()
    reconcile(client, report_with_changes())
    number, issue, _ = current_issue(client)
    issue["state"] = "closed"
    client.mutations.clear()

    reconcile(client, report_with_changes(live_checksum="live-b"))

    assert client.issue_values[number]["state"] == "open"
    assert ("patch", number) in client.mutations
    assert len(client.comment_values[number]) == 1


@pytest.mark.integration
def test_new_lock_campaign_creates_new_issue_and_closes_old() -> None:
    client = FakeGitHubClient()
    report = report_with_changes()
    reconcile(client, report)
    old_number, _, _ = current_issue(client)
    new_lock = {"documents": [{"link": "two.html", "sections": [{"id": "fls_two"}]}]}
    client.mutations.clear()

    assert (
        reconciliation.reconcile(client, report, "# Report\n", new_lock, "fls-audit", "FLS audit:")
        == "Reconciled audit issue #2001."
    )

    assert len(client.issue_values) == 2
    assert client.mutations == [("create", 2001), ("comment", 2000), ("patch", 2000)]
    assert client.issue_values[old_number]["state"] == "closed"
    assert len(client.comment_values[old_number]) == 1
