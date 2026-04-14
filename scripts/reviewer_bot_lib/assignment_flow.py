"""Confirmation-gated reviewer authority transitions."""

from __future__ import annotations

from .config import CODING_GUIDELINE_LABEL
from .guidance import (
    get_assignment_failure_comment,
    get_fls_audit_guidance,
    get_generic_issue_guidance,
    get_issue_guidance,
    get_pr_guidance,
)
from .review_state import (
    clear_current_reviewer,
    ensure_review_entry,
    set_current_reviewer,
)


def _log(bot, level: str, message: str, **fields) -> None:
    bot.logger.event(level, message, **fields)


def _now_iso(bot) -> str:
    return bot.clock.now().isoformat()


def _normalize_logins(values: list[str] | None) -> list[str]:
    if not isinstance(values, list):
        return []
    return [value.lower() for value in values if isinstance(value, str)]


def _success_attempt(bot, status_code: int = 200):
    return bot.AssignmentAttempt(success=True, status_code=status_code)


def _coerce_attempt(bot, result, *, success_status: int) -> object:
    if isinstance(result, bool):
        if result:
            return _success_attempt(bot, success_status)
        return bot.AssignmentAttempt(success=False, status_code=None)
    return result


def _post_assignment_guidance(bot, request, reviewer: str) -> None:
    if request.is_pull_request:
        bot.github.post_comment(request.issue_number, get_pr_guidance(reviewer, request.issue_author))
        return
    labels = set(request.issue_labels)
    guidance = (
        get_fls_audit_guidance(reviewer, request.issue_author)
        if bot.FLS_AUDIT_LABEL in labels
        else get_issue_guidance(reviewer, request.issue_author)
        if CODING_GUIDELINE_LABEL in labels
        else get_generic_issue_guidance(reviewer, request.issue_author)
    )
    bot.github.post_comment(request.issue_number, guidance)


def _remove_live_assignee(bot, request, issue_number: int, username: str):
    if request.is_pull_request:
        return _coerce_attempt(bot, bot.github.remove_pr_reviewer(issue_number, username), success_status=204)
    return _coerce_attempt(bot, bot.github.remove_issue_assignee(issue_number, username), success_status=204)


def _add_live_assignee(bot, request, issue_number: int, username: str):
    if request.is_pull_request:
        return _coerce_attempt(bot, bot.github.request_pr_reviewer_assignment(issue_number, username), success_status=201)
    return _coerce_attempt(bot, bot.github.assign_issue_assignee(issue_number, username), success_status=201)


def confirm_reviewer_assignment(
    bot,
    state: dict,
    request,
    *,
    reviewer: str,
    assignment_method: str,
    cycle_started_at: str | None = None,
    current_assignees: list[str] | None = None,
    record_assignment: bool = True,
    emit_guidance: bool = True,
    emit_failure_comment: bool = True,
    pr_head_sha: str | None = None,
) -> dict[str, object]:
    issue_number = request.issue_number
    live_before = current_assignees
    if live_before is None:
        live_before = bot.github.get_issue_assignees(issue_number)
    if live_before is None:
        return {"confirmed": False, "reason": "assignees_unavailable"}
    if request.issue_author and reviewer.lower() == request.issue_author.lower():
        return {
            "confirmed": False,
            "reason": "self_review_not_allowed",
            "current_assignees": live_before,
        }
    removal_attempts = {}
    live_before_normalized = _normalize_logins(live_before)
    for assignee in live_before:
        if assignee.lower() == reviewer.lower():
            continue
        attempt = _remove_live_assignee(bot, request, issue_number, assignee)
        removal_attempts[assignee] = attempt
        if not attempt.success:
            final_assignees = bot.github.get_issue_assignees(issue_number)
            return {
                "confirmed": False,
                "reason": "remove_failed",
                "current_assignees": live_before,
                "final_assignees": final_assignees,
                "removal_attempts": removal_attempts,
            }
    assignment_attempt = None
    if reviewer.lower() not in live_before_normalized:
        assignment_attempt = _add_live_assignee(bot, request, issue_number, reviewer)
    final_assignees = bot.github.get_issue_assignees(issue_number)
    if final_assignees is None:
        return {
            "confirmed": False,
            "reason": "final_assignees_unknown",
            "current_assignees": live_before,
            "assignment_attempt": assignment_attempt,
            "removal_attempts": removal_attempts,
        }
    final_normalized = _normalize_logins(final_assignees)
    if len(final_assignees) == 1 and final_normalized[0] == reviewer.lower():
        set_current_reviewer(
            state,
            issue_number,
            reviewer,
            assignment_method=assignment_method,
            at=cycle_started_at or _now_iso(bot),
        )
        review_data = ensure_review_entry(state, issue_number, create=True)
        if request.is_pull_request and isinstance(review_data, dict) and isinstance(pr_head_sha, str) and pr_head_sha:
            review_data["active_head_sha"] = pr_head_sha
        if record_assignment:
            bot.adapters.queue.record_assignment(
                state,
                reviewer,
                issue_number,
                "pr" if request.is_pull_request else "issue",
            )
        if emit_guidance:
            _post_assignment_guidance(bot, request, reviewer)
        return {
            "confirmed": True,
            "reviewer": reviewer,
            "current_assignees": live_before,
            "final_assignees": final_assignees,
            "assignment_attempt": assignment_attempt or _success_attempt(bot),
            "removal_attempts": removal_attempts,
        }
    cleared = False
    if len(final_assignees) != 1:
        cleared = clear_current_reviewer(state, issue_number)
    failure_comment = None
    if assignment_attempt is not None and not assignment_attempt.success:
        failure_comment = get_assignment_failure_comment(
            reviewer,
            assignment_attempt,
            is_pull_request=request.is_pull_request,
        )
        if emit_failure_comment and failure_comment:
            bot.github.post_comment(issue_number, failure_comment)
    return {
        "confirmed": False,
        "reason": "final_assignee_mismatch",
        "current_assignees": live_before,
        "final_assignees": final_assignees,
        "assignment_attempt": assignment_attempt,
        "removal_attempts": removal_attempts,
        "failure_comment": failure_comment,
        "cleared_current_reviewer": cleared,
    }


def confirm_reviewer_release(
    bot,
    state: dict,
    request,
    *,
    reviewer: str,
    reposition_reviewer: bool = False,
) -> dict[str, object]:
    issue_number = request.issue_number
    live_before = bot.github.get_issue_assignees(issue_number)
    if live_before is None:
        return {"confirmed": False, "reason": "assignees_unavailable"}
    removal_attempt = None
    if reviewer.lower() in _normalize_logins(live_before):
        removal_attempt = _remove_live_assignee(bot, request, issue_number, reviewer)
        if not removal_attempt.success:
            return {
                "confirmed": False,
                "reason": "remove_failed",
                "current_assignees": live_before,
                "removal_attempt": removal_attempt,
            }
    final_assignees = bot.github.get_issue_assignees(issue_number)
    if final_assignees is None:
        return {
            "confirmed": False,
            "reason": "final_assignees_unknown",
            "current_assignees": live_before,
            "removal_attempt": removal_attempt,
        }
    if final_assignees:
        return {
            "confirmed": False,
            "reason": "final_assignee_mismatch",
            "current_assignees": live_before,
            "final_assignees": final_assignees,
            "removal_attempt": removal_attempt,
        }
    cleared = clear_current_reviewer(state, issue_number)
    if reposition_reviewer:
        bot.adapters.queue.reposition_member_as_next(state, reviewer)
    return {
        "confirmed": True,
        "current_assignees": live_before,
        "final_assignees": final_assignees,
        "removal_attempt": removal_attempt or _success_attempt(bot, status_code=204),
        "cleared_current_reviewer": cleared,
    }


def clear_reviewer_authority(bot, state: dict, issue_number: int, *, reason: str) -> bool:
    changed = clear_current_reviewer(state, issue_number)
    if changed:
        _log(bot, "warning", f"Cleared reviewer authority for #{issue_number}: {reason}", issue_number=issue_number, reason=reason)
    return changed
