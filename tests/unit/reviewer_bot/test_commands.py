
from pathlib import Path

import pytest

from scripts.reviewer_bot_core import privileged_command_policy
from scripts.reviewer_bot_lib import (
    automation,
    commands,
    comment_application,
    comment_routing,
    guidance,
    reconcile,
    review_state,
)
from scripts.reviewer_bot_lib.config import FLS_AUDIT_LABEL
from tests.fixtures.commands_harness import CommandHarness
from tests.fixtures.comment_routing_harness import CommentRoutingHarness
from tests.fixtures.reviewer_bot import make_state


def test_label_signoff_create_pr_marks_issue_review_complete_without_inline_status_sync(monkeypatch):
    harness = CommandHarness(monkeypatch)
    assert harness.github is harness.runtime.github
    assert harness.handlers is harness.runtime.handlers
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /label +sign-off: create pr",
        issue_author="dana",
        is_pull_request=False,
        issue_labels=("coding guideline",),
    )
    harness.runtime.github.get_repo_labels = lambda: ["sign-off: create pr"]
    harness.runtime.github.add_label = lambda issue_number, label: True
    harness.runtime.sync_status_labels_for_items = lambda *args, **kwargs: pytest.fail(
        "status sync should run only from app orchestration after save"
    )
    harness.runtime.github.add_reaction = lambda *args, **kwargs: True
    posted = harness.capture_posted_comments()

    assert harness.handle_comment_event(state, request=request) is True
    assert review["review_completion_source"] == "issue_label: sign-off: create pr"
    assert review["current_cycle_completion"]["completed"] is True
    assert posted == [(42, "✅ Added label `sign-off: create pr`")]


def test_label_signoff_create_pr_on_generic_issue_does_not_mark_issue_complete(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /label +sign-off: create pr",
        issue_author="dana",
        is_pull_request=False,
        issue_labels=(),
    )
    harness.runtime.github.get_repo_labels = lambda: ["sign-off: create pr"]
    harness.runtime.github.add_label = lambda issue_number, label: True
    harness.runtime.github.add_reaction = lambda *args, **kwargs: True
    harness.runtime.github.post_comment = lambda *args, **kwargs: True

    assert harness.handle_comment_event(state, request=request) is False
    assert review["review_completion_source"] is None


def test_label_signoff_create_pr_on_pr_does_not_mark_issue_complete(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /label +sign-off: create pr",
        issue_author="dana",
        is_pull_request=True,
    )
    trust_context = harness.typed_trust_context(
        author_association="MEMBER",
        workflow_file=".github/workflows/reviewer-bot-pr-comment-router.yml",
        repository="rustfoundation/safety-critical-rust-coding-guidelines",
        ref="refs/heads/main",
    )
    harness.runtime.github_api = lambda method, endpoint, data=None: {
        "head": {"repo": {"full_name": "rustfoundation/safety-critical-rust-coding-guidelines"}},
        "user": {"login": "dana"},
        "pull_request": {},
    }
    harness.runtime.github.get_repo_labels = lambda: ["sign-off: create pr"]
    harness.runtime.github.add_label = lambda issue_number, label: True
    harness.runtime.sync_status_labels_for_items = lambda *args, **kwargs: pytest.fail(
        "status sync should not run for PR sign-off label command"
    )
    harness.runtime.github.add_reaction = lambda *args, **kwargs: True
    harness.runtime.github.post_comment = lambda *args, **kwargs: True

    assert harness.handle_comment_event(state, request=request, trust_context=trust_context) is False
    assert review["review_completion_source"] is None


def test_create_pull_request_fails_closed_when_open_pr_lookup_unavailable(monkeypatch):
    harness = CommandHarness(monkeypatch)
    called = {"post": 0}
    harness.runtime.set_config_value("REPO_OWNER", "rustfoundation")
    harness.runtime.github_api_request = lambda method, endpoint, data=None, extra_headers=None, **kwargs: harness.runtime.GitHubApiResult(
        502, {"message": "bad gateway"}, {}, "bad gateway", False, "server_error", 1, None
    )
    harness.runtime.github_api = lambda method, endpoint, data=None: called.__setitem__("post", called["post"] + 1) or None

    with pytest.raises(RuntimeError, match="Unable to determine whether branch 'feature-branch' already has an open PR"):
        automation.create_pull_request(harness.runtime, "feature-branch", "main", 42)

    assert called["post"] == 0


def test_assign_command_fails_closed_when_assignees_unavailable(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [{"github": "felix91gr", "name": "Félix Fischer"}]
    harness.runtime.github.get_issue_assignees = lambda issue_number: None

    response, success = harness.handle_assign(state, 42, "@felix91gr")

    assert success is False
    assert "Unable to determine current assignees/reviewers" in response


def test_assign_command_posts_pr_guidance_on_success(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [{"github": "felix91gr", "name": "Félix Fischer"}]
    request = harness.typed_assignment_request(issue_number=42, issue_author="PLeVasseur", is_pull_request=True)
    harness.stub_assignees([])
    harness.stub_assignment()
    posted = []
    harness.runtime.github.post_comment = lambda issue_number, body: posted.append(body) or True

    response, success = harness.handle_assign(state, 42, "@felix91gr", request=request)

    assert success is True
    assert response == "✅ @felix91gr has been assigned as reviewer."
    assert posted == [guidance.get_pr_guidance("felix91gr", "PLeVasseur")]


def test_claim_command_posts_pr_guidance_on_success(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [{"github": "felix91gr", "name": "Félix Fischer"}]
    request = harness.typed_assignment_request(issue_number=42, issue_author="PLeVasseur", is_pull_request=True)
    harness.stub_assignees([])
    harness.stub_assignment()
    posted = []
    harness.runtime.github.post_comment = lambda issue_number, body: posted.append(body) or True

    response, success = harness.handle_claim(state, 42, "felix91gr", request=request)

    assert success is True
    assert response == "✅ @felix91gr has claimed this review."
    assert posted == [guidance.get_pr_guidance("felix91gr", "PLeVasseur")]


def test_assign_command_uses_guidance_owner_for_fls_issue_guidance(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [{"github": "felix91gr", "name": "Félix Fischer"}]
    request = harness.typed_assignment_request(
        issue_number=42,
        issue_author="PLeVasseur",
        is_pull_request=False,
        issue_labels=(FLS_AUDIT_LABEL,),
    )
    harness.stub_assignees([])
    harness.stub_assignment()
    harness.runtime.get_fls_audit_guidance = lambda *args, **kwargs: pytest.fail(
        "commands.py should use guidance.get_fls_audit_guidance directly"
    )
    posted = []
    harness.runtime.github.post_comment = lambda issue_number, body: posted.append(body) or True

    response, success = harness.handle_assign(state, 42, "@felix91gr", request=request)

    assert success is True
    assert response == "✅ @felix91gr has been assigned as reviewer."
    assert posted == [guidance.get_fls_audit_guidance("felix91gr", "PLeVasseur")]


def test_pass_command_posts_pr_guidance_for_new_reviewer(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [
        {"github": "alice", "name": "Alice"},
        {"github": "felix91gr", "name": "Félix Fischer"},
    ]
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    request = harness.typed_assignment_request(issue_number=42, issue_author="PLeVasseur", is_pull_request=True)
    harness.stub_assignees(["alice"])
    harness.stub_assignment()
    posted = []
    harness.runtime.github.post_comment = lambda issue_number, body: posted.append(body) or True

    response, success = harness.handle_pass(state, 42, "alice", None, request=request)

    assert success is True
    assert "@felix91gr is now assigned as the reviewer." in response
    assert posted == [guidance.get_pr_guidance("felix91gr", "PLeVasseur")]


def test_pass_command_accepts_confirmed_pr_reviewer_when_live_reviewers_are_empty(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [
        {"github": "alice", "name": "Alice"},
        {"github": "bob", "name": "Bob"},
    ]
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    request = harness.typed_assignment_request(issue_number=42, issue_author="dana", is_pull_request=True)
    harness.stub_assignees([])
    harness.stub_assignment()
    posted = []
    harness.runtime.github.post_comment = lambda issue_number, body: posted.append(body) or True

    response, success = harness.handle_pass(state, 42, "alice", None, request=request)

    assert success is True
    assert "@bob is now assigned as the reviewer." in response
    assert review["current_reviewer"] == "bob"
    assert posted == [guidance.get_pr_guidance("bob", "dana")]


def test_release_command_accepts_confirmed_pr_reviewer_when_live_reviewers_are_empty(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    review["assignment_method"] = "round-robin"
    request = harness.typed_assignment_request(issue_number=42, issue_author="dana", is_pull_request=True)
    harness.stub_assignees([])

    response, success = harness.handle_release(state, 42, "alice", request=request)

    assert success is True
    assert "@alice has released this review" in response
    assert review["current_reviewer"] is None


def test_release_command_resolves_reviewer_authority_before_triage_fallback(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "bob"
    harness.stub_assignees(["bob"])
    calls = []
    original_resolver = commands.assignment_flow.resolve_reviewer_command_authority

    def resolve_with_order(*args, **kwargs):
        calls.append("resolver")
        return original_resolver(*args, **kwargs)

    monkeypatch.setattr(commands.assignment_flow, "resolve_reviewer_command_authority", resolve_with_order)
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": calls.append("permission") or "granted"

    response, success = harness.handle_release(state, 42, "alice", ["@bob"])

    assert success is True
    assert "@alice has released @bob" in response
    assert calls[:2] == ["resolver", "permission"]


def test_rectify_command_accepts_confirmed_pr_reviewer_when_live_reviewers_are_empty(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    harness.runtime.set_config_value("IS_PULL_REQUEST", "true")
    harness.stub_assignees([])
    calls = []
    monkeypatch.setattr(
        reconcile,
        "reconcile_active_review_entry",
        lambda bot, current_state, issue_number: calls.append((bot, current_state, issue_number)) or ("rectified", True, False),
    )

    message, success, changed = harness.handle_rectify(state, 42, "alice")

    assert (message, success, changed) == ("rectified", True, False)
    assert calls == [(harness.runtime, state, 42)]


def test_rectify_command_resolves_reviewer_authority_before_triage_fallback(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    harness.stub_assignees([])
    calls = []
    original_resolver = reconcile.assignment_flow.resolve_reviewer_command_authority

    def resolve_with_order(*args, **kwargs):
        calls.append("resolver")
        return original_resolver(*args, **kwargs)

    monkeypatch.setattr(reconcile.assignment_flow, "resolve_reviewer_command_authority", resolve_with_order)
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": calls.append("permission") or "granted"
    monkeypatch.setattr(
        reconcile,
        "reconcile_active_review_entry",
        lambda bot, current_state, issue_number: calls.append("reconcile") or ("rectified", True, False),
    )

    message, success, changed = harness.handle_rectify(state, 42, "maintainer")

    assert (message, success, changed) == ("rectified", True, False)
    assert calls == ["resolver", "permission", "reconcile"]


def test_assign_from_queue_posts_guidance_only_once(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [{"github": "felix91gr", "name": "Félix Fischer"}]
    request = harness.typed_assignment_request(issue_number=42, issue_author="PLeVasseur", is_pull_request=True)
    harness.stub_assignees([])
    harness.stub_assignment()
    posted = []
    harness.runtime.github.post_comment = lambda issue_number, body: posted.append(body) or True

    response, success = harness.handle_assign_from_queue(state, 42, request=request)

    assert success is True
    assert response == "✅ @felix91gr (next in queue) has been assigned as reviewer."
    assert posted == [guidance.get_pr_guidance("felix91gr", "PLeVasseur")]


def test_done_command_marks_generic_issue_review_complete_for_current_reviewer(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    request = harness.typed_assignment_request(issue_number=42, issue_author="dana", is_pull_request=False, issue_labels=())
    harness.stub_assignees(["alice"])

    response, success = commands.handle_done_command(harness.runtime, state, 42, "alice", request=request)

    assert success is True
    assert response == "✅ Review marked complete."
    assert review["review_completion_source"] == "command: /done"


def test_done_command_rejects_pull_requests(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    request = harness.typed_assignment_request(issue_number=42, issue_author="dana", is_pull_request=True, issue_labels=())

    response, success = commands.handle_done_command(harness.runtime, state, 42, "alice", request=request)

    assert success is False
    assert "not supported on pull requests" in response


def test_done_command_rejects_coding_guideline_issues(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    request = harness.typed_assignment_request(
        issue_number=42,
        issue_author="dana",
        is_pull_request=False,
        issue_labels=("coding guideline",),
    )

    response, success = commands.handle_done_command(harness.runtime, state, 42, "alice", request=request)

    assert success is False
    assert "Use `sign-off: create pr`" in response


def test_done_command_allows_triage_maintainer_when_current_reviewer_differs(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    request = harness.typed_assignment_request(issue_number=42, issue_author="dana", is_pull_request=False, issue_labels=(FLS_AUDIT_LABEL,))
    harness.stub_assignees(["alice"])
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": "granted"

    response, success = commands.handle_done_command(harness.runtime, state, 42, "bob", request=request)

    assert success is True
    assert response == "✅ Review marked complete."
    assert review["review_completed_by"] == "bob"


def test_pass_command_does_not_mutate_reviewer_state_when_remove_fails(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [
        {"github": "alice", "name": "Alice"},
        {"github": "bob", "name": "Bob"},
    ]
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    review["skipped"] = []
    harness.stub_assignees(["alice"])
    harness.runtime.github.remove_issue_assignee = lambda issue_number, username: False

    response, success = harness.handle_pass(state, 42, "alice", None)

    assert success is False
    assert "could not confirm @bob as reviewer" in response
    assert review["current_reviewer"] == "alice"
    assert review["skipped"] == []


def test_release_command_does_not_clear_reviewer_state_when_remove_fails(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    harness.stub_assignees(["alice"])
    harness.runtime.github.remove_issue_assignee = lambda issue_number, username: False

    response, success = harness.handle_release(state, 42, "alice")

    assert success is False
    assert "could not confirm @alice as reviewer" in response
    assert review["current_reviewer"] == "alice"


def test_away_command_does_not_mutate_queue_when_reassignment_is_unconfirmed(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [
        {"github": "alice", "name": "Alice"},
        {"github": "bob", "name": "Bob"},
    ]
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    harness.stub_assignees(["alice"])
    harness.runtime.github.remove_issue_assignee = lambda issue_number, username: False

    response, success = harness.handle_pass_until(state, 42, "alice", "2099-01-01", None)

    assert success is False
    assert "could not confirm @bob as reviewer" in response
    assert [member["github"] for member in state["queue"]] == ["alice", "bob"]
    assert state["pass_until"] == []


def test_handle_accept_no_fls_changes_command_fails_closed_when_permission_unavailable(monkeypatch):
    harness = CommandHarness(monkeypatch)
    request = harness.typed_privileged_request(
        issue_number=42,
        actor="alice",
        command_name="accept-no-fls-changes",
        is_pull_request=False,
        issue_labels=(FLS_AUDIT_LABEL,),
    )
    harness.stub_permission("unavailable")

    message, success = harness.handle_accept_no_fls_changes(42, "alice", request=request)

    assert success is False
    assert "Unable to verify triage permissions right now" in message


def test_i1_comment_application_consumes_typed_ordinary_command_result(monkeypatch):
    module_text = Path("scripts/reviewer_bot_lib/comment_application.py").read_text(encoding="utf-8")

    assert "ORDINARY_COMMAND_HANDLERS" in module_text
    assert "decision.command_id" in module_text
    assert "decision.needs_assignment_request" in module_text
    assert "CommandExecutionResult" in module_text


def test_k2_comment_application_entrypoints_use_narrow_comment_runtime_protocol():
    module_text = Path("scripts/reviewer_bot_lib/comment_application.py").read_text(encoding="utf-8")

    assert "CommentApplicationRuntimeContext" in module_text
    assert "bot: CommentApplicationRuntimeContext" in module_text


def test_pass_command_fails_closed_when_assignees_unavailable(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    harness.runtime.github.get_issue_assignees = lambda issue_number: None

    response, success = harness.handle_pass(state, 42, "alice", None)

    assert success is False
    assert "Unable to determine current assignees/reviewers" in response


def test_away_command_fails_closed_when_assignees_unavailable(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [{"github": "alice", "name": "Alice"}, {"github": "bob", "name": "Bob"}]
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    harness.runtime.github.get_issue_assignees = lambda issue_number: None

    response, success = harness.handle_pass_until(state, 42, "alice", "2099-01-01", None)

    assert success is False
    assert "Unable to determine current assignees/reviewers" in response


def test_claim_command_fails_closed_when_assignees_unavailable(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [{"github": "alice", "name": "Alice"}]
    harness.runtime.github.get_issue_assignees = lambda issue_number: None

    response, success = harness.handle_claim(state, 42, "alice")

    assert success is False
    assert "Unable to determine current assignees/reviewers" in response


def test_release_command_fails_closed_when_permission_unavailable(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "bob"
    harness.stub_assignees(["bob"])
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": "unavailable"

    response, success = harness.handle_release(state, 42, "alice", ["@bob"])

    assert success is False
    assert "Unable to verify triage permissions right now" in response


def test_release_command_fails_closed_when_assignees_unavailable(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    harness.runtime.github.get_issue_assignees = lambda issue_number: None

    response, success = harness.handle_release(state, 42, "alice")

    assert success is False
    assert "Unable to determine current assignees/reviewers" in response


def test_assign_from_queue_command_fails_closed_when_assignees_unavailable(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    state["queue"] = [{"github": "alice", "name": "Alice"}]
    harness.runtime.github.get_issue_assignees = lambda issue_number: None

    response, success = harness.handle_assign_from_queue(state, 42)

    assert success is False
    assert "Unable to determine current assignees/reviewers" in response


def test_handle_rectify_command_reports_permission_unavailable(monkeypatch):
    state = make_state()
    harness = CommandHarness(monkeypatch)
    monkeypatch.setattr(reconcile, "ensure_review_entry", lambda current, issue_number, create=False: None)
    harness.runtime.github.get_issue_assignees = lambda issue_number: []
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": "unavailable"

    message, success, changed = harness.handle_rectify(state, 42, "alice")

    assert success is False
    assert changed is False
    assert "Unable to verify triage permissions right now" in message


def test_handle_rectify_command_reports_permission_denied(monkeypatch):
    state = make_state()
    harness = CommandHarness(monkeypatch)
    monkeypatch.setattr(reconcile, "ensure_review_entry", lambda current, issue_number, create=False: None)
    harness.runtime.github.get_issue_assignees = lambda issue_number: []
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": "denied"

    message, success, changed = harness.handle_rectify(state, 42, "alice")

    assert success is False
    assert changed is False
    assert "Only maintainers with triage+ permission" in message


def test_handle_rectify_command_uses_live_assignee_truth_over_stored_reviewer(monkeypatch):
    state = make_state()
    harness = CommandHarness(monkeypatch)
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    harness.runtime.github.get_issue_assignees = lambda issue_number: ["bob"]
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": "denied"

    message, success, changed = harness.handle_rectify(state, 42, "alice")

    assert success is False
    assert changed is False
    assert "@bob" in message


def test_validate_accept_no_fls_changes_handoff_distinguishes_permission_unavailable(monkeypatch):
    harness = CommentRoutingHarness(monkeypatch)
    harness.runtime.set_config_value("ISSUE_LABELS", f'["{FLS_AUDIT_LABEL}"]')
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": "unavailable"
    request = harness.request(
        issue_number=42,
        is_pull_request=False,
        issue_labels=(FLS_AUDIT_LABEL,),
        comment_author="alice",
        comment_body="@guidelines-bot /accept-no-fls-changes",
    )

    decision = privileged_command_policy.validate_accept_no_fls_changes_handoff(
        request,
        "unavailable",
        source_event_key="issue_comment:100",
    )

    assert decision == privileged_command_policy.BlockedPrivilegedHandoff(
        reason="authorization_unavailable",
        response="❌ Unable to verify triage permissions right now; refusing to run this command.",
    )


@pytest.mark.parametrize(
    ("is_pull_request", "labels", "permission", "expected_reason"),
    [
        (True, (FLS_AUDIT_LABEL,), "granted", "pull_request_target_not_allowed"),
        (False, (), "granted", "missing_fls_audit_label"),
        (False, (FLS_AUDIT_LABEL,), "denied", "authorization_failed"),
    ],
)
def test_validate_accept_no_fls_changes_handoff_freezes_fail_closed_reason_matrix(
    monkeypatch,
    is_pull_request,
    labels,
    permission,
    expected_reason,
):
    harness = CommentRoutingHarness(monkeypatch)
    harness.runtime.set_config_value("ISSUE_LABELS", str(list(labels)).replace("'", '"'))
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": permission
    request = harness.request(
        issue_number=42,
        is_pull_request=is_pull_request,
        issue_labels=labels,
        comment_author="alice",
        comment_body="@guidelines-bot /accept-no-fls-changes",
    )

    decision = privileged_command_policy.validate_accept_no_fls_changes_handoff(
        request,
        permission,
        source_event_key="issue_comment:100",
    )

    assert decision.reason == expected_reason


def test_validate_accept_no_fls_changes_handoff_freezes_success_metadata_shape(monkeypatch):
    harness = CommentRoutingHarness(monkeypatch)
    harness.runtime.set_config_value("ISSUE_LABELS", f'["{FLS_AUDIT_LABEL}"]')
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": "granted"
    request = harness.request(
        issue_number=42,
        is_pull_request=False,
        issue_labels=(FLS_AUDIT_LABEL,),
        comment_author="alice",
        comment_body="@guidelines-bot /accept-no-fls-changes",
    )

    decision = privileged_command_policy.validate_accept_no_fls_changes_handoff(
        request,
        "granted",
        source_event_key="issue_comment:100",
    )

    assert decision == privileged_command_policy.AllowedPrivilegedHandoff(
        source_event_key="issue_comment:100",
        command_name=privileged_command_policy.PrivilegedCommandId.ACCEPT_NO_FLS_CHANGES.value,
        issue_number=42,
        actor="alice",
        authorization_required_permission="triage",
        authorization_authorized=True,
        target_kind="issue",
        target_number=42,
        target_labels_snapshot=(FLS_AUDIT_LABEL,),
    )


def test_apply_comment_command_records_privileged_handoff_side_effects(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    side_effects = harness.capture_comment_side_effects()
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /accept-no-fls-changes",
        issue_author="dana",
        is_pull_request=False,
        issue_labels=(FLS_AUDIT_LABEL,),
    )
    harness.stub_permission("granted")

    changed = comment_application.apply_comment_command(
        harness.runtime,
        state,
        request,
        {"command": "accept-no-fls-changes", "args": [], "command_count": 1},
        classify_issue_comment_actor=lambda current_request: "repo_user_principal",
    )

    pending = state["active_reviews"]["42"]["sidecars"]["pending_privileged_commands"]["issue_comment:100"]
    assert changed is True
    assert pending["command_name"] == "accept-no-fls-changes"
    assert pending["status"] == "pending"
    assert pending["authorization_authorized"] is True
    assert side_effects.comments == [
        (
            42,
            "✅ Recorded pending privileged command `accept-no-fls-changes` from trusted live validation. Use the isolated privileged workflow to execute it from issue `the configured state issue` state.",
        )
    ]
    assert side_effects.reactions == []


def test_apply_comment_command_adds_reactions_and_posts_normalized_queue_response(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    side_effects = harness.capture_comment_side_effects()
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /queue",
        issue_author="dana",
        is_pull_request=False,
    )
    monkeypatch.setattr(commands, "handle_queue_command", lambda bot, current_state: ("queue snapshot", True))

    changed = comment_application.apply_comment_command(
        harness.runtime,
        state,
        request,
        {"command": "queue", "args": [], "command_count": 1},
        classify_issue_comment_actor=lambda current_request: "repo_user_principal",
    )

    assert changed is False
    assert side_effects.comments == [(42, "queue snapshot")]
    assert side_effects.reactions == [(100, "eyes"), (100, "+1")]


def test_feedback_command_records_issue_reviewer_handoff_without_channel_acceptance(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    review["assigned_at"] = "2026-03-17T09:00:00Z"
    harness.stub_assignees(["alice"])
    side_effects = harness.capture_comment_side_effects()
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /feedback",
        issue_author="dana",
        is_pull_request=False,
    )

    changed = comment_application.apply_comment_command(
        harness.runtime,
        state,
        request,
        {"command": "feedback", "args": [], "command_count": 1},
        classify_issue_comment_actor=lambda current_request: "repo_user_principal",
    )

    assert changed is True
    assert review["current_cycle_reviewer_handoff"] == {
        "source_event_key": "issue_comment:100",
        "timestamp": "2026-03-17T10:00:00Z",
        "actor": "alice",
        "command_name": "feedback",
        "reviewed_head_sha": None,
    }
    assert review["reviewer_comment"]["accepted"] is None
    assert review["assigned_at"] == "2026-03-17T09:00:00Z"
    assert side_effects.comments == [
        (42, "✅ Recorded reviewer feedback handoff. Reviewer-bot is now waiting on contributor response.")
    ]
    assert side_effects.reactions == [(100, "eyes"), (100, "+1")]


def test_feedback_command_accepts_confirmed_pr_reviewer_when_live_reviewers_are_empty(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    review["active_head_sha"] = "head-1"
    harness.stub_assignees([])
    side_effects = harness.capture_comment_side_effects()
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /feedback",
        issue_author="dana",
        is_pull_request=True,
    )

    changed = comment_application.apply_comment_command(
        harness.runtime,
        state,
        request,
        {"command": "feedback", "args": [], "command_count": 1},
        classify_issue_comment_actor=lambda current_request: "repo_user_principal",
    )

    assert changed is True
    assert review["current_cycle_reviewer_handoff"]["reviewed_head_sha"] == "head-1"
    assert side_effects.comments == [
        (42, "✅ Recorded reviewer feedback handoff. Reviewer-bot is now waiting on contributor response.")
    ]


def test_feedback_command_rejects_triage_actor_who_is_not_current_reviewer(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    review["active_head_sha"] = "head-1"
    harness.stub_assignees([])
    harness.stub_permission("granted")
    side_effects = harness.capture_comment_side_effects()
    request = harness.typed_comment_request(
        issue_number=42,
        actor="maintainer",
        body="@guidelines-bot /feedback",
        issue_author="dana",
        is_pull_request=True,
    )

    changed = comment_application.apply_comment_command(
        harness.runtime,
        state,
        request,
        {"command": "feedback", "args": [], "command_count": 1},
        classify_issue_comment_actor=lambda current_request: "repo_user_principal",
    )

    assert changed is False
    assert review["current_cycle_reviewer_handoff"] is None
    assert side_effects.comments == [(42, "❌ Only the current reviewer (@alice) can use `/feedback`.")]
    assert side_effects.reactions == [(100, "eyes")]


def test_feedback_command_does_not_materialize_review_entry_when_no_active_review(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    harness.stub_assignees([])
    side_effects = harness.capture_comment_side_effects()
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /feedback",
        issue_author="dana",
        is_pull_request=False,
    )

    changed = comment_application.apply_comment_command(
        harness.runtime,
        state,
        request,
        {"command": "feedback", "args": [], "command_count": 1},
        classify_issue_comment_actor=lambda current_request: "repo_user_principal",
    )

    assert changed is False
    assert "42" not in state["active_reviews"]
    assert side_effects.comments == [(42, "❌ No active tracked review exists for this issue/PR.")]
    assert side_effects.reactions == [(100, "eyes")]


def test_feedback_command_does_not_overwrite_newer_handoff(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    review["current_cycle_reviewer_handoff"] = {
        "source_event_key": "issue_comment:101",
        "timestamp": "2026-03-17T11:00:00Z",
        "actor": "alice",
        "command_name": "feedback",
        "reviewed_head_sha": None,
    }
    harness.stub_assignees(["alice"])
    side_effects = harness.capture_comment_side_effects()
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /feedback",
        issue_author="dana",
        is_pull_request=False,
        comment_id=100,
        created_at="2026-03-17T10:00:00Z",
    )

    changed = comment_application.apply_comment_command(
        harness.runtime,
        state,
        request,
        {"command": "feedback", "args": [], "command_count": 1},
        classify_issue_comment_actor=lambda current_request: "repo_user_principal",
    )

    assert changed is False
    assert review["current_cycle_reviewer_handoff"] == {
        "source_event_key": "issue_comment:101",
        "timestamp": "2026-03-17T11:00:00Z",
        "actor": "alice",
        "command_name": "feedback",
        "reviewed_head_sha": None,
    }
    assert side_effects.comments == [
        (42, "ℹ️ Ignored stale `/feedback` handoff because a newer or same-time reviewer handoff is already recorded.")
    ]
    assert side_effects.reactions == [(100, "eyes"), (100, "+1")]


def test_feedback_command_does_not_overwrite_same_timestamp_different_event(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    review["current_cycle_reviewer_handoff"] = {
        "source_event_key": "issue_comment:100",
        "timestamp": "2026-03-17T10:00:00Z",
        "actor": "alice",
        "command_name": "feedback",
        "reviewed_head_sha": None,
    }
    harness.stub_assignees(["alice"])
    side_effects = harness.capture_comment_side_effects()
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /feedback",
        issue_author="dana",
        is_pull_request=False,
        comment_id=101,
        created_at="2026-03-17T10:00:00Z",
    )

    changed = comment_application.apply_comment_command(
        harness.runtime,
        state,
        request,
        {"command": "feedback", "args": [], "command_count": 1},
        classify_issue_comment_actor=lambda current_request: "repo_user_principal",
    )

    assert changed is False
    assert review["current_cycle_reviewer_handoff"]["source_event_key"] == "issue_comment:100"
    assert side_effects.comments == [
        (42, "ℹ️ Ignored stale `/feedback` handoff because a newer or same-time reviewer handoff is already recorded.")
    ]


def test_feedback_command_replays_same_event_idempotently(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    review["last_reviewer_activity"] = "2026-03-17T10:00:00Z"
    review["current_cycle_reviewer_handoff"] = {
        "source_event_key": "issue_comment:100",
        "timestamp": "2026-03-17T10:00:00Z",
        "actor": "alice",
        "command_name": "feedback",
        "reviewed_head_sha": None,
    }
    harness.stub_assignees(["alice"])
    harness.capture_comment_side_effects()
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /feedback",
        issue_author="dana",
        is_pull_request=False,
        comment_id=100,
        created_at="2026-03-17T10:00:00Z",
    )

    changed = comment_application.apply_comment_command(
        harness.runtime,
        state,
        request,
        {"command": "feedback", "args": [], "command_count": 1},
        classify_issue_comment_actor=lambda current_request: "repo_user_principal",
    )

    assert changed is False
    assert review["current_cycle_reviewer_handoff"] == {
        "source_event_key": "issue_comment:100",
        "timestamp": "2026-03-17T10:00:00Z",
        "actor": "alice",
        "command_name": "feedback",
        "reviewed_head_sha": None,
    }


def test_feedback_command_overwrites_older_handoff(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    review["current_cycle_reviewer_handoff"] = {
        "source_event_key": "issue_comment:100",
        "timestamp": "2026-03-17T09:00:00Z",
        "actor": "alice",
        "command_name": "feedback",
        "reviewed_head_sha": None,
    }
    harness.stub_assignees(["alice"])
    harness.capture_comment_side_effects()
    request = harness.typed_comment_request(
        issue_number=42,
        actor="alice",
        body="@guidelines-bot /feedback",
        issue_author="dana",
        is_pull_request=False,
        comment_id=101,
        created_at="2026-03-17T10:00:00Z",
    )

    changed = comment_application.apply_comment_command(
        harness.runtime,
        state,
        request,
        {"command": "feedback", "args": [], "command_count": 1},
        classify_issue_comment_actor=lambda current_request: "repo_user_principal",
    )

    assert changed is True
    assert review["current_cycle_reviewer_handoff"] == {
        "source_event_key": "issue_comment:101",
        "timestamp": "2026-03-17T10:00:00Z",
        "actor": "alice",
        "command_name": "feedback",
        "reviewed_head_sha": None,
    }


def test_feedback_command_plus_text_does_not_record_reviewer_comment_channel(monkeypatch):
    harness = CommentRoutingHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    harness.runtime.github.get_issue_assignees = lambda issue_number: ["alice"]
    harness.runtime.github.get_issue_assignees_result = lambda issue_number, is_pull_request=None: harness.runtime.GitHubApiResult(
        200,
        ["alice"],
        {},
        "ok",
        True,
        None,
        0,
        None,
    )
    side_effects = harness.capture_comment_side_effects()
    request = harness.request(
        issue_number=42,
        is_pull_request=False,
        issue_author="dana",
        comment_author="alice",
        comment_body="@guidelines-bot /feedback\nadditional feedback text",
    )

    changed = comment_application.process_comment_event(
        harness.runtime,
        state,
        request,
        classify_comment_payload=comment_routing.classify_comment_payload,
        classify_issue_comment_actor=comment_routing.classify_issue_comment_actor,
    )

    assert changed is True
    assert review["current_cycle_reviewer_handoff"]["command_name"] == "feedback"
    assert review["reviewer_comment"]["accepted"] is None
    assert side_effects.comments == [
        (42, "✅ Recorded reviewer feedback handoff. Reviewer-bot is now waiting on contributor response.")
    ]


def test_feedback_command_with_arguments_rejects_without_channel_mutation(monkeypatch):
    harness = CommentRoutingHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["current_reviewer"] = "alice"
    side_effects = harness.capture_comment_side_effects()
    request = harness.request(
        issue_number=42,
        is_pull_request=False,
        issue_author="dana",
        comment_author="alice",
        comment_body="@guidelines-bot /feedback please",
    )

    changed = comment_application.process_comment_event(
        harness.runtime,
        state,
        request,
        classify_comment_payload=comment_routing.classify_comment_payload,
        classify_issue_comment_actor=comment_routing.classify_issue_comment_actor,
    )

    assert changed is False
    assert review["current_cycle_reviewer_handoff"] is None
    assert review["reviewer_comment"]["accepted"] is None
    assert side_effects.comments == [(42, "❌ `/feedback` does not accept arguments. Usage: `@guidelines-bot /feedback`")]


def test_manual_dispatch_marks_authorization_unavailable_for_pending_privileged_command(monkeypatch):
    harness = CommandHarness(monkeypatch)
    state = make_state()
    review = review_state.ensure_review_entry(state, 42, create=True)
    assert review is not None
    review["sidecars"]["pending_privileged_commands"] = {
        "issue_comment:100": {
            "source_event_key": "issue_comment:100",
            "command_name": "accept-no-fls-changes",
            "issue_number": 42,
            "actor": "alice",
            "authorization_required_permission": "triage",
            "authorization_authorized": True,
            "target_kind": "issue",
            "target_number": 42,
            "target_labels_snapshot": [FLS_AUDIT_LABEL],
            "status": "pending",
            "created_at": "2026-03-17T10:00:00Z",
        }
    }
    harness.set_manual_dispatch(source_event_key="issue_comment:100")
    harness.runtime.github.get_issue_or_pr_snapshot = lambda issue_number: {"number": issue_number, "labels": [{"name": FLS_AUDIT_LABEL}]}
    harness.runtime.github.get_user_permission_status = lambda username, required_permission="triage": "unavailable"

    assert harness.handle_manual_dispatch(state) is True
    pending = review["sidecars"]["pending_privileged_commands"]["issue_comment:100"]
    assert pending["status"] == "failed_closed"
    assert pending["result_code"] == "authorization_unavailable"


@pytest.mark.parametrize(
    ("comment_body", "expected"),
    [
        ("@guidelines-bot /queue", ("queue", [])),
        ("@guidelines-bot /feedback", ("feedback", [])),
        ("@guidelines-bot /feedback please", ("_malformed_feedback_args", [])),
        ("@guidelines-bot /r? producers", ("assign-from-queue", [])),
        ("@guidelines-bot /r? @alice", ("r?-user", ["@alice"])),
        ("@guidelines-bot queue", ("_malformed_known", ["queue"])),
        ("@guidelines-bot /queue\n@guidelines-bot /pass", ("_multiple_commands", [])),
        ("@guidelines-bot hello", None),
    ],
)
def test_parse_command_preserves_known_command_classification(monkeypatch, comment_body, expected):
    harness = CommandHarness(monkeypatch)
    parser_bot = type(
        "ParserBot",
        (),
        {
            "BOT_MENTION": harness.runtime.BOT_MENTION,
            "COMMANDS": {
                "queue",
                "pass",
                "feedback",
                "label",
                "away",
                "claim",
                "release",
                "rectify",
                "sync-members",
                "accept-no-fls-changes",
            },
        },
    )()

    assert commands.parse_command(parser_bot, comment_body) == expected


def test_parse_command_preserves_quoted_args(monkeypatch):
    harness = CommandHarness(monkeypatch)

    parser_bot = type("ParserBot", (), {"BOT_MENTION": harness.runtime.BOT_MENTION, "COMMANDS": {"label"}})()

    assert commands.parse_command(parser_bot, '@guidelines-bot /label +"needs decision"') == ("label", ["+needs decision"])


def test_strip_code_blocks_removes_fenced_indented_and_inline_code(monkeypatch):
    comment_body = """before
```bash
@guidelines-bot /queue
```
    @guidelines-bot /queue
inline `@guidelines-bot /queue`
after"""

    assert commands.strip_code_blocks(comment_body) == "before\n\n\ninline \nafter"


def test_comment_application_delegates_ordinary_command_decision_to_core_policy():
    module_text = Path("scripts/reviewer_bot_lib/comment_application.py").read_text(encoding="utf-8")

    assert "comment_command_policy" in module_text
    assert "decision = comment_command_policy.decide_comment_command(" in module_text


def test_h1_feedback_command_surface_keeps_inline_execution_owner_explicit():
    module_text = Path("scripts/reviewer_bot_lib/comment_application.py").read_text(encoding="utf-8")

    assert "def handle_feedback_command(" in module_text
    assert "handle_feedback_command(bot, state, request, decision)" in module_text
    assert "assignment_flow.resolve_reviewer_command_authority(" in module_text


def test_commands_module_exposes_rectify_handler_for_decision_adapter_surface():
    assert hasattr(commands, "handle_rectify_command") is False


def test_comment_application_and_automation_delegate_privileged_planning_to_core_policy():
    comment_application_text = Path("scripts/reviewer_bot_lib/comment_application.py").read_text(encoding="utf-8")
    automation_text = Path("scripts/reviewer_bot_lib/automation.py").read_text(encoding="utf-8")

    assert "privileged_command_policy" in comment_application_text
    assert "privileged_command_policy.validate_accept_no_fls_changes_handoff(" in comment_application_text
    assert "privileged_command_policy.build_pending_privileged_command(" in comment_application_text
    assert "from scripts.reviewer_bot_core import privileged_command_policy" in automation_text
    assert "privileged_command_policy.prevalidate_accept_no_fls_changes_request(" in automation_text
    assert "privileged_command_policy.plan_accept_no_fls_changes_execution(" in automation_text
