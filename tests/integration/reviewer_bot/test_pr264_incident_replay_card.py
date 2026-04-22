import pytest

from scripts.reviewer_bot_lib import maintenance
from tests.fixtures.reconcile_harness import ReconcileHarness, issue_comment_payload
from tests.fixtures.reviewer_bot import (
    make_state,
    make_tracked_review_state,
    pull_request_payload,
)
from tests.fixtures.reviewer_bot_fakes import RouteGitHubApi

pytestmark = pytest.mark.integration


def test_pr264_canonical_replay_card_suppresses_same_scope_reviewer_activity_after_reconcile(monkeypatch):
    state = make_state()
    review = make_tracked_review_state(
        state,
        264,
        reviewer="iglesias",
        assigned_at="2026-02-10T17:20:07Z",
        active_cycle_started_at="2026-02-10T17:20:07Z",
    )
    harness = ReconcileHarness(
        monkeypatch,
        issue_comment_payload(
            pr_number=264,
            comment_id=210,
            source_event_key="issue_comment:210",
            body="LGTM",
            comment_class="plain_text",
            has_non_command_text=True,
            source_created_at="2026-04-13T23:23:25Z",
            actor_login="iglesias",
            source_run_id=610,
            source_run_attempt=1,
        ),
    )
    harness.add_pull_request(pr_number=264, head_sha="head-live", author="manhatsu", labels=["coding guideline"], requested_reviewers=[])
    harness.add_issue_comment(
        comment_id=210,
        body="LGTM",
        author="iglesias",
        author_type="User",
        author_association="CONTRIBUTOR",
    )

    assert harness.run(state) is True
    assert review["reviewer_comment"]["accepted"]["semantic_key"] == "issue_comment:210"

    routes = RouteGitHubApi().add_request(
        "GET",
        "issues/264",
        status_code=200,
        payload={"number": 264, "state": "open", "pull_request": {}, "labels": []},
    ).add_request(
        "GET",
        "pulls/264",
        status_code=200,
        payload={
            **pull_request_payload(264, head_sha="head-live", author="manhatsu"),
            "requested_reviewers": [],
            "labels": [],
        },
    ).add_pull_request_reviews(264, [])
    harness.runtime.github.stub(routes)

    overdue = maintenance.check_overdue_reviews(harness.runtime, state)
    response_state = harness.runtime.adapters.review_state.compute_reviewer_response_state(
        264,
        review,
        issue_snapshot={"number": 264, "state": "open", "pull_request": {}, "labels": []},
    )

    assert overdue == []
    assert response_state["state"] == "awaiting_contributor_response"
    assert response_state["reason"] == "accepted_same_scope_reviewer_activity"
    assert response_state["suppression_reason"] == "accepted_same_scope_reviewer_activity"
    assert response_state["current_scope_basis"] == "active_cycle_started_at"
    assert response_state["current_scope_key"] == "reviewer=iglesias|head=head-live|cycle=2026-02-10T17:20:07Z|anchor=2026-02-10T17:20:07Z"
