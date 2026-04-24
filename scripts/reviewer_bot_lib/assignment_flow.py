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
from .repair_records import clear_repair_marker, store_repair_marker
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
        return bot.AssignmentAttempt(success=False, status_code=None, failure_kind="transport_error")
    return result


def _store_assignment_marker(bot, review_data: dict, issue_number: int, *, phase: str, marker: dict) -> bool:
    changed = store_repair_marker(review_data, phase, marker)
    if changed:
        bot.collect_touched_item(issue_number)
    return changed


def _clear_assignment_marker(bot, review_data: dict, issue_number: int, *, phase: str) -> bool:
    changed = clear_repair_marker(review_data, phase)
    if changed:
        bot.collect_touched_item(issue_number)
    return changed


def _assignment_attempt_marker(bot, *, phase: str, attempt) -> dict:
    return {
        "kind": "reminder_transport_failure",
        "phase": phase,
        "status_code": attempt.status_code,
        "failure_kind": attempt.failure_kind or "transport_error",
        "retry_attempts": attempt.retry_attempts,
        "recorded_at": bot.clock.now().isoformat(),
    }


def _assignment_authority_mismatch_marker(bot, *, live_assignees: list[str], reason: str) -> dict:
    return {
        "kind": "reviewer_authority_mismatch",
        "phase": "assignment_confirm_read",
        "status_code": None,
        "failure_kind": "reviewer_authority_mismatch",
        "retry_attempts": 0,
        "recorded_at": bot.clock.now().isoformat(),
        "reason": reason,
        "live_assignees": list(live_assignees),
    }


def _hard_fail_if_permission_denied(result, *, action: str, issue_number: int) -> None:
    if result.failure_kind in {"unauthorized", "forbidden"}:
        raise RuntimeError(
            f"Permission denied during {action} for #{issue_number} (status {result.status_code})."
        )


def _read_live_assignees(bot, state: dict, issue_number: int, *, is_pull_request: bool | None = None):
    review_data = ensure_review_entry(state, issue_number, create=True)
    result = bot.github.get_issue_assignees_result(issue_number, is_pull_request=is_pull_request)
    diagnostic_changed = False
    _hard_fail_if_permission_denied(result, action="assignee confirmation read", issue_number=issue_number)
    if not result.ok or not isinstance(result.payload, list):
        if isinstance(review_data, dict):
            diagnostic_changed = _store_assignment_marker(
                bot,
                review_data,
                issue_number,
                phase="assignment_confirm_read",
                marker=_assignment_attempt_marker(bot, phase="assignment_confirm_read", attempt=result),
            )
        return review_data, None, result, diagnostic_changed
    if isinstance(review_data, dict):
        diagnostic_changed = _clear_assignment_marker(bot, review_data, issue_number, phase="assignment_confirm_read")
    return review_data, result.payload, result, diagnostic_changed


def resolve_reviewer_authority(
    bot,
    issue_number: int,
    review_data: dict,
    *,
    is_pull_request: bool,
) -> dict[str, object]:
    tracked_reviewer = review_data.get("current_reviewer") if isinstance(review_data, dict) else None
    result = bot.github.get_issue_assignees_result(issue_number, is_pull_request=is_pull_request)
    _hard_fail_if_permission_denied(result, action="reviewer authority read", issue_number=issue_number)
    if not result.ok or not isinstance(result.payload, list):
        return {
            "authority_status": "live_read_unavailable",
            "tracked_reviewer": tracked_reviewer,
            "live_control_plane_reviewers": [],
            "reason": str(result.failure_kind or "live_control_plane_unavailable"),
        }

    live_control_plane_reviewers = [value for value in result.payload if isinstance(value, str) and value.strip()]
    if not isinstance(tracked_reviewer, str) or not tracked_reviewer.strip():
        return {
            "authority_status": "no_tracked_reviewer",
            "tracked_reviewer": None,
            "live_control_plane_reviewers": live_control_plane_reviewers,
            "reason": "no_tracked_reviewer",
        }
    normalized_reviewers = {value.lower() for value in live_control_plane_reviewers}
    tracked_key = tracked_reviewer.lower()
    if is_pull_request:
        if normalized_reviewers and tracked_key not in normalized_reviewers:
            return {
                "authority_status": "control_plane_mismatch",
                "tracked_reviewer": tracked_reviewer,
                "live_control_plane_reviewers": live_control_plane_reviewers,
                "reason": "tracked_reviewer_missing_from_live_control_plane",
            }
        return {
            "authority_status": "tracked_reviewer_confirmed",
            "tracked_reviewer": tracked_reviewer,
            "live_control_plane_reviewers": live_control_plane_reviewers,
            "reason": "tracked_reviewer_confirmed",
        }

    if len(live_control_plane_reviewers) != 1:
        return {
            "authority_status": "control_plane_mismatch",
            "tracked_reviewer": tracked_reviewer,
            "live_control_plane_reviewers": live_control_plane_reviewers,
            "reason": "invalid_live_assignee_count",
        }
    if tracked_key != live_control_plane_reviewers[0].lower():
        return {
            "authority_status": "control_plane_mismatch",
            "tracked_reviewer": tracked_reviewer,
            "live_control_plane_reviewers": live_control_plane_reviewers,
            "reason": "stored_reviewer_mismatch",
        }
    return {
        "authority_status": "tracked_reviewer_confirmed",
        "tracked_reviewer": tracked_reviewer,
        "live_control_plane_reviewers": live_control_plane_reviewers,
        "reason": "tracked_reviewer_confirmed",
    }


def resolve_reviewer_command_authority(
    bot,
    state: dict,
    request,
    *,
    actor: str | None = None,
) -> dict[str, object]:
    issue_number = request.issue_number
    review_data = ensure_review_entry(state, issue_number)
    if review_data is None:
        result = bot.github.get_issue_assignees_result(issue_number, is_pull_request=bool(request.is_pull_request))
        _hard_fail_if_permission_denied(result, action="reviewer authority read", issue_number=issue_number)
        if not result.ok or not isinstance(result.payload, list):
            return {
                "authorized": False,
                "authorization_status": "live_read_unavailable",
                "review_data": None,
                "tracked_reviewer": None,
                "live_control_plane_reviewers": [],
                "reason": str(result.failure_kind or "live_control_plane_unavailable"),
            }
        return {
            "authorized": False,
            "authorization_status": "no_active_review",
            "review_data": None,
            "tracked_reviewer": None,
            "live_control_plane_reviewers": [value for value in result.payload if isinstance(value, str) and value.strip()],
            "reason": "no_active_review",
        }
    authority = resolve_reviewer_authority(
        bot,
        issue_number,
        review_data,
        is_pull_request=bool(request.is_pull_request),
    )
    status = str(authority.get("authority_status"))
    resolution = {
        "authorized": status == "tracked_reviewer_confirmed",
        "authorization_status": status,
        "review_data": review_data,
        "tracked_reviewer": authority.get("tracked_reviewer"),
        "live_control_plane_reviewers": list(authority.get("live_control_plane_reviewers") or []),
        "reason": authority.get("reason"),
    }
    if not resolution["authorized"] or actor is None:
        return resolution
    return require_reviewer_command_actor(resolution, actor)


def require_reviewer_command_actor(resolution: dict[str, object], actor: str) -> dict[str, object]:
    if not resolution.get("authorized"):
        return resolution
    tracked_reviewer = resolution.get("tracked_reviewer")
    if isinstance(tracked_reviewer, str) and tracked_reviewer.lower() == actor.lower():
        return resolution
    denied = dict(resolution)
    denied["authorized"] = False
    denied["authorization_status"] = "actor_not_current_reviewer"
    denied["reason"] = "actor_not_current_reviewer"
    return denied


def reviewer_command_authority_failure_message(command_name: str, resolution: dict[str, object]) -> str:
    status = str(resolution.get("authorization_status") or "")
    tracked_reviewer = resolution.get("tracked_reviewer")
    live_reviewers = [value for value in resolution.get("live_control_plane_reviewers") or [] if isinstance(value, str)]
    if status == "live_read_unavailable":
        return "❌ Unable to determine current assignees/reviewers from GitHub; refusing to continue."
    if status in {"no_active_review", "no_tracked_reviewer"}:
        return "❌ No active tracked review exists for this issue/PR."
    if status == "actor_not_current_reviewer" and isinstance(tracked_reviewer, str) and tracked_reviewer:
        return f"❌ Only the current reviewer (@{tracked_reviewer}) can use `/{command_name}`."
    if status == "control_plane_mismatch":
        if live_reviewers:
            return (
                f"❌ Unable to confirm @{tracked_reviewer} as the current reviewer from GitHub. "
                f"Live reviewer(s): @{', @'.join(live_reviewers)}."
            )
        return f"❌ Unable to confirm @{tracked_reviewer} as the current reviewer from GitHub."
    return f"❌ Unable to confirm current reviewer authority for `/{command_name}`."


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
    review_data = ensure_review_entry(state, issue_number, create=True)
    stored_reviewer = review_data.get("current_reviewer") if isinstance(review_data, dict) else None
    diagnostic_changed = False
    live_before = current_assignees
    if live_before is None:
        review_data, live_before, _, marker_changed = _read_live_assignees(
            bot,
            state,
            issue_number,
            is_pull_request=request.is_pull_request,
        )
        diagnostic_changed = marker_changed or diagnostic_changed
    if live_before is None:
        return {
            "confirmed": False,
            "reason": "assignees_unavailable",
            "diagnostic_changed": diagnostic_changed,
        }
    if request.issue_author and reviewer.lower() == request.issue_author.lower():
        if isinstance(review_data, dict):
            diagnostic_changed = _store_assignment_marker(
                bot,
                review_data,
                issue_number,
                phase="assignment_confirm_read",
                marker=_assignment_authority_mismatch_marker(
                    bot,
                    live_assignees=live_before,
                    reason="self_review_not_allowed",
                ),
            ) or diagnostic_changed
        return {
            "confirmed": False,
            "reason": "self_review_not_allowed",
            "current_assignees": live_before,
            "diagnostic_changed": diagnostic_changed,
        }
    removal_attempts = {}
    live_before_normalized = _normalize_logins(live_before)
    for assignee in live_before:
        if assignee.lower() == reviewer.lower():
            continue
        attempt = _remove_live_assignee(bot, request, issue_number, assignee)
        removal_attempts[assignee] = attempt
        if not attempt.success:
            if isinstance(review_data, dict):
                diagnostic_changed = _store_assignment_marker(
                    bot,
                    review_data,
                    issue_number,
                    phase="assignment_remove_write",
                    marker=_assignment_attempt_marker(bot, phase="assignment_remove_write", attempt=attempt),
                ) or diagnostic_changed
            _, final_assignees, _, marker_changed = _read_live_assignees(
                bot,
                state,
                issue_number,
                is_pull_request=request.is_pull_request,
            )
            diagnostic_changed = marker_changed or diagnostic_changed
            return {
                "confirmed": False,
                "reason": "remove_failed",
                "current_assignees": live_before,
                "final_assignees": final_assignees,
                "removal_attempts": removal_attempts,
                "diagnostic_changed": diagnostic_changed,
            }
    assignment_attempt = None
    if reviewer.lower() not in live_before_normalized:
        assignment_attempt = _add_live_assignee(bot, request, issue_number, reviewer)
        if not assignment_attempt.success and isinstance(review_data, dict):
            diagnostic_changed = _store_assignment_marker(
                bot,
                review_data,
                issue_number,
                phase="assignment_add_write",
                marker=_assignment_attempt_marker(bot, phase="assignment_add_write", attempt=assignment_attempt),
            ) or diagnostic_changed
    review_data, final_assignees, _, marker_changed = _read_live_assignees(
        bot,
        state,
        issue_number,
        is_pull_request=request.is_pull_request,
    )
    diagnostic_changed = marker_changed or diagnostic_changed
    if final_assignees is None:
        return {
            "confirmed": False,
            "reason": "final_assignees_unknown",
            "current_assignees": live_before,
            "assignment_attempt": assignment_attempt,
            "removal_attempts": removal_attempts,
            "diagnostic_changed": diagnostic_changed,
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
        bot.collect_touched_item(issue_number)
        if isinstance(review_data, dict):
            diagnostic_changed = _clear_assignment_marker(bot, review_data, issue_number, phase="assignment_add_write") or diagnostic_changed
            diagnostic_changed = _clear_assignment_marker(bot, review_data, issue_number, phase="assignment_remove_write") or diagnostic_changed
            diagnostic_changed = _clear_assignment_marker(bot, review_data, issue_number, phase="assignment_confirm_read") or diagnostic_changed
        return {
            "confirmed": True,
            "reviewer": reviewer,
            "current_assignees": live_before,
            "final_assignees": final_assignees,
            "assignment_attempt": assignment_attempt or _success_attempt(bot),
            "removal_attempts": removal_attempts,
            "diagnostic_changed": diagnostic_changed,
        }
    cleared = False
    if len(final_assignees) != 1 or (
        len(final_assignees) == 1
        and isinstance(stored_reviewer, str)
        and final_normalized[0] != stored_reviewer.lower()
    ):
        cleared = clear_current_reviewer(state, issue_number)
        if cleared:
            bot.collect_touched_item(issue_number)
    if isinstance(review_data, dict):
        diagnostic_changed = _store_assignment_marker(
            bot,
            review_data,
            issue_number,
            phase="assignment_confirm_read",
            marker=_assignment_authority_mismatch_marker(
                bot,
                live_assignees=final_assignees,
                reason="final_assignee_mismatch",
            ),
        ) or diagnostic_changed
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
        "diagnostic_changed": diagnostic_changed,
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
    review_data = ensure_review_entry(state, issue_number, create=True)
    stored_reviewer = review_data.get("current_reviewer") if isinstance(review_data, dict) else None
    review_data, live_before, _, diagnostic_changed = _read_live_assignees(
        bot,
        state,
        issue_number,
        is_pull_request=request.is_pull_request,
    )
    if live_before is None:
        return {
            "confirmed": False,
            "reason": "assignees_unavailable",
            "diagnostic_changed": diagnostic_changed,
        }
    removal_attempt = None
    if reviewer.lower() in _normalize_logins(live_before):
        removal_attempt = _remove_live_assignee(bot, request, issue_number, reviewer)
        if not removal_attempt.success:
            if isinstance(review_data, dict):
                diagnostic_changed = _store_assignment_marker(
                    bot,
                    review_data,
                    issue_number,
                    phase="assignment_remove_write",
                    marker=_assignment_attempt_marker(bot, phase="assignment_remove_write", attempt=removal_attempt),
                ) or diagnostic_changed
            return {
                "confirmed": False,
                "reason": "remove_failed",
                "current_assignees": live_before,
                "removal_attempt": removal_attempt,
                "diagnostic_changed": diagnostic_changed,
            }
    review_data, final_assignees, _, marker_changed = _read_live_assignees(
        bot,
        state,
        issue_number,
        is_pull_request=request.is_pull_request,
    )
    diagnostic_changed = marker_changed or diagnostic_changed
    if final_assignees is None:
        return {
            "confirmed": False,
            "reason": "final_assignees_unknown",
            "current_assignees": live_before,
            "removal_attempt": removal_attempt,
            "diagnostic_changed": diagnostic_changed,
        }
    if final_assignees:
        cleared = False
        if len(final_assignees) != 1 or (
            len(final_assignees) == 1
            and isinstance(stored_reviewer, str)
            and final_assignees[0].lower() != stored_reviewer.lower()
        ):
            cleared = clear_current_reviewer(state, issue_number)
            if cleared:
                bot.collect_touched_item(issue_number)
        if isinstance(review_data, dict):
            diagnostic_changed = _store_assignment_marker(
                bot,
                review_data,
                issue_number,
                phase="assignment_confirm_read",
                marker=_assignment_authority_mismatch_marker(
                    bot,
                    live_assignees=final_assignees,
                    reason="final_assignee_mismatch",
                ),
            ) or diagnostic_changed
        return {
            "confirmed": False,
            "reason": "final_assignee_mismatch",
            "current_assignees": live_before,
            "final_assignees": final_assignees,
            "removal_attempt": removal_attempt,
            "cleared_current_reviewer": cleared,
            "diagnostic_changed": diagnostic_changed,
        }
    cleared = clear_current_reviewer(state, issue_number)
    if cleared:
        bot.collect_touched_item(issue_number)
    if reposition_reviewer:
        bot.adapters.queue.reposition_member_as_next(state, reviewer)
    if isinstance(review_data, dict):
        diagnostic_changed = _clear_assignment_marker(bot, review_data, issue_number, phase="assignment_remove_write") or diagnostic_changed
        diagnostic_changed = _clear_assignment_marker(bot, review_data, issue_number, phase="assignment_confirm_read") or diagnostic_changed
    return {
        "confirmed": True,
        "current_assignees": live_before,
        "final_assignees": final_assignees,
        "removal_attempt": removal_attempt or _success_attempt(bot, status_code=204),
        "cleared_current_reviewer": cleared,
        "diagnostic_changed": diagnostic_changed,
    }


def clear_reviewer_authority(bot, state: dict, issue_number: int, *, reason: str) -> bool:
    changed = clear_current_reviewer(state, issue_number)
    if changed:
        _log(bot, "warning", f"Cleared reviewer authority for #{issue_number}: {reason}", issue_number=issue_number, reason=reason)
    return changed
