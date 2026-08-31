import copy

import pytest

from scripts.fls_audit_issue_lib import reconcile as reconciliation
from scripts.fls_audit_issue_lib.errors import AuditIssueError
from scripts.fls_audit_issue_lib.state import parse_state
from tests.fls_audit_fixtures import report_with_changes, spec_lock
from tests.integration.fls_audit.fake_github import BOT_USER, FakeGitHubClient


def reconcile(client: FakeGitHubClient, report: dict) -> str:
    return reconciliation.reconcile(client, report, "# Report\n", spec_lock(), "fls-audit", "FLS audit:")


def predecessor_issue(number: int, state: str = "closed") -> dict:
    return {
        "number": number,
        "title": "FLS audit: changes detected (2026-08-27)",
        "body": (
            "## What to do\npredecessor\n\n# FLS Spec Lock Audit Report\n\n"
            f"- Baseline commit: `{'b' * 40}`\n"
        ),
        "labels": [{"name": "fls-audit"}],
        "state": state,
        "user": copy.deepcopy(BOT_USER),
    }


def clean_report() -> dict:
    report = report_with_changes()
    report["changes"] = {"added": [], "removed": [], "changed": []}
    report["affected_guidelines"] = {}
    report["summary"] = dict.fromkeys(report["summary"], 0)
    report["text"] = {"added": {}, "removed": {}, "content_diffs": []}
    return report


@pytest.mark.integration
def test_closed_stateless_predecessors_are_untouched_history() -> None:
    client = FakeGitHubClient()
    oversized = predecessor_issue(1199)
    oversized["body"] = "historical report\n" + ("x" * 60_001)
    predecessors = {
        1236: predecessor_issue(1236),
        1200: predecessor_issue(1200),
        1199: oversized,
    }
    client.issue_values.update(copy.deepcopy(predecessors))

    assert reconcile(client, report_with_changes()) == "Reconciled audit issue #2000."

    assert set(client.issue_values) == {1199, 1200, 1236, 2000}
    for number, predecessor in predecessors.items():
        assert client.issue_values[number] == predecessor
    assert client.mutations == [("create", 2000)]
    assert parse_state(client.issue_values[2000]["body"]) is not None

    client.mutations.clear()
    assert reconcile(client, report_with_changes()) == "Audit issue #2000 is already current."
    assert client.mutations == []


@pytest.mark.integration
def test_clean_report_leaves_closed_stateless_history_untouched() -> None:
    client = FakeGitHubClient()
    predecessors = {1236: predecessor_issue(1236), 1200: predecessor_issue(1200)}
    client.issue_values.update(copy.deepcopy(predecessors))

    assert reconcile(client, clean_report()) == "No changes found and no current campaign issue exists."

    assert client.issue_values == predecessors
    assert client.mutations == []


@pytest.mark.integration
def test_non_closed_stateless_predecessor_fails_before_mutation() -> None:
    client = FakeGitHubClient()
    client.label_exists = False
    client.issue_values[1200] = predecessor_issue(1200, "open")

    with pytest.raises(
        AuditIssueError,
        match="Non-closed bot-owned FLS audit issues have no valid campaign state: #1200",
    ):
        reconcile(client, report_with_changes())

    assert client.label_exists is False
    assert client.mutations == []


@pytest.mark.integration
def test_malformed_managed_marker_in_closed_history_still_fails_closed() -> None:
    client = FakeGitHubClient()
    issue = predecessor_issue(1200)
    issue["body"] += "\n<!-- fls-audit:state:v1\n{}\n-->\n"
    client.issue_values[1200] = issue

    with pytest.raises(AuditIssueError, match="state marker is outside its managed region"):
        reconcile(client, report_with_changes())

    assert client.mutations == []
