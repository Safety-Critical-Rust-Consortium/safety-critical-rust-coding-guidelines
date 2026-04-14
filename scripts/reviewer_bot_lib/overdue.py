"""Overdue review domain logic for reviewer-bot."""

from __future__ import annotations

from .config import TRANSITION_NOTICE_MARKER_PREFIX, TRANSITION_WARNING_MARKER_PREFIX
from .repair_records import clear_repair_marker, store_repair_marker

_TRANSITION_NOTICE_AUTHORS = {"github-actions[bot]", "guidelines-bot"}


def _log(bot, level: str, message: str, **fields) -> None:
    bot.logger.event(level, message, **fields)


def _warning_anchor_sentence(bot, reviewer: str, anchor_reason: str | None) -> str:
    if anchor_reason in {"contributor_comment_newer", "contributor_revision_newer"}:
        return (
            f"Hey @{reviewer}, it's been more than {bot.REVIEW_DEADLINE_DAYS} days since the latest "
            "contributor follow-up returned this review to you."
        )
    return f"Hey @{reviewer}, it's been more than {bot.REVIEW_DEADLINE_DAYS} days since you were assigned to review this."


def _transport_marker(*, phase: str, result, recorded_at: str) -> dict:
    return {
        "kind": "reminder_transport_failure",
        "phase": phase,
        "status_code": result.status_code,
        "failure_kind": result.failure_kind,
        "retry_attempts": result.retry_attempts,
        "recorded_at": recorded_at,
    }


def _record_transport_failure(bot, review_data: dict, issue_number: int, *, phase: str, result) -> bool:
    changed = store_repair_marker(
        review_data,
        phase,
        _transport_marker(phase=phase, result=result, recorded_at=bot.clock.now().isoformat()),
    )
    if changed:
        bot.collect_touched_item(issue_number)
    return changed


def _clear_transport_failure(bot, review_data: dict, issue_number: int, *, phase: str) -> bool:
    changed = clear_repair_marker(review_data, phase)
    if changed:
        bot.collect_touched_item(issue_number)
    return changed


def _warning_marker(issue_number: int, reviewer: str, anchor_timestamp: str | None) -> str:
    return (
        f"<!-- {TRANSITION_WARNING_MARKER_PREFIX} issue={issue_number} reviewer={reviewer} "
        f"anchor={anchor_timestamp or ''} -->"
    )


def _authority_marker(*, phase: str, live_assignees: list[str], reason: str, recorded_at: str) -> dict:
    return {
        "kind": "reviewer_authority_mismatch",
        "phase": phase,
        "status_code": None,
        "failure_kind": "reviewer_authority_mismatch",
        "retry_attempts": 0,
        "recorded_at": recorded_at,
        "reason": reason,
        "live_assignees": list(live_assignees),
    }


def _find_existing_marker_comment(
    bot,
    issue_number: int,
    marker: str,
    *,
    authors: set[str],
    not_before: str | None = None,
) -> dict[str, object]:
    earliest = None
    if isinstance(not_before, str) and not_before:
        try:
            earliest = bot.datetime.fromisoformat(not_before.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            earliest = None
    page = 1
    while True:
        response = bot.github.list_issue_comments_result(issue_number, page=page)
        if not response.ok or not isinstance(response.payload, list):
            return {
                "status": "unavailable",
                "status_code": response.status_code,
                "failure_kind": response.failure_kind,
                "retry_attempts": response.retry_attempts,
            }
        first_match = None
        for comment in response.payload:
            if not isinstance(comment, dict):
                continue
            user = comment.get("user")
            login = user.get("login") if isinstance(user, dict) else None
            created_at = comment.get("created_at")
            body = comment.get("body")
            if not isinstance(login, str) or not isinstance(created_at, str) or not isinstance(body, str):
                continue
            if login not in authors:
                continue
            try:
                created_dt = bot.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            if earliest is not None and created_dt < earliest:
                continue
            lines = body.splitlines()
            first_line = lines[0].strip() if lines else ""
            if first_line == marker:
                if first_match is None or created_dt < first_match[0]:
                    first_match = (created_dt, created_at)
        if first_match is not None:
            return {"status": "found", "timestamp": first_match[1]}
        if len(response.payload) < 100:
            break
        page += 1
    return {"status": "missing"}


def _warning_scan_result(bot, issue_number: int, reviewer: str, anchor_timestamp: str | None) -> dict[str, object]:
    return _find_existing_marker_comment(
        bot,
        issue_number,
        _warning_marker(issue_number, reviewer, anchor_timestamp),
        authors=_TRANSITION_NOTICE_AUTHORS,
    )


def check_overdue_reviews_result(bot, state: dict) -> tuple[list[dict], bool]:
    overdue = check_overdue_reviews(bot, state)
    return overdue, False


def check_overdue_reviews(bot, state: dict) -> list[dict]:
    """Check all active reviews for overdue ones."""
    if "active_reviews" not in state:
        return []

    now = bot.datetime.now(bot.timezone.utc)
    overdue = []

    for issue_key, review_data in state["active_reviews"].items():
        if not isinstance(review_data, dict):
            continue

        if review_data.get("review_completed_at"):
            continue

        if review_data.get("transition_notice_sent_at"):
            continue

        current_reviewer = review_data.get("current_reviewer")
        if not current_reviewer:
            continue

        issue_number = int(issue_key)
        issue_snapshot_result = bot.github.get_issue_or_pr_snapshot_result(issue_number)
        issue_snapshot = issue_snapshot_result.payload if issue_snapshot_result.ok else None
        if not isinstance(issue_snapshot, dict):
            if issue_snapshot_result.failure_kind in {"unauthorized", "forbidden"}:
                raise RuntimeError(
                    f"Permission denied reading issue snapshot for #{issue_number} (status {issue_snapshot_result.status_code})."
                )
            _record_transport_failure(
                bot,
                review_data,
                issue_number,
                phase="issue_snapshot_read",
                result=issue_snapshot_result,
            )
            _log(bot, "warning", f"Skipping overdue evaluation for #{issue_number}; issue/PR snapshot unavailable", issue_number=issue_number)
            continue
        _clear_transport_failure(bot, review_data, issue_number, phase="issue_snapshot_read")
        if str(issue_snapshot.get("state", "")).lower() == "closed":
            continue
        assignee_result = bot.github.get_issue_assignees_result(
            issue_number,
            is_pull_request=isinstance(issue_snapshot.get("pull_request"), dict),
        )
        if assignee_result.failure_kind in {"unauthorized", "forbidden"}:
            raise RuntimeError(
                f"Permission denied reading reviewer authority for #{issue_number} (status {assignee_result.status_code})."
            )
        if not assignee_result.ok or not isinstance(assignee_result.payload, list):
            _record_transport_failure(
                bot,
                review_data,
                issue_number,
                phase="assignment_confirm_read",
                result=assignee_result,
            )
            continue
        live_assignees = assignee_result.payload
        live_assignees_normalized = [assignee.lower() for assignee in live_assignees]
        if len(live_assignees) != 1:
            _store_assignment_marker = store_repair_marker(
                review_data,
                "assignment_confirm_read",
                _authority_marker(
                    phase="assignment_confirm_read",
                    live_assignees=live_assignees,
                    reason="invalid_live_assignee_count",
                    recorded_at=bot.clock.now().isoformat(),
                ),
            )
            if _store_assignment_marker:
                bot.collect_touched_item(issue_number)
            continue
        if current_reviewer.lower() != live_assignees_normalized[0]:
            _store_assignment_marker = store_repair_marker(
                review_data,
                "assignment_confirm_read",
                _authority_marker(
                    phase="assignment_confirm_read",
                    live_assignees=live_assignees,
                    reason="stored_reviewer_mismatch",
                    recorded_at=bot.clock.now().isoformat(),
                ),
            )
            if _store_assignment_marker:
                bot.collect_touched_item(issue_number)
            continue
        _clear_transport_failure(bot, review_data, issue_number, phase="assignment_confirm_read")
        response_state = bot.adapters.review_state.compute_reviewer_response_state(
            issue_number,
            review_data,
            issue_snapshot=issue_snapshot,
        )
        if response_state.get("state") != "awaiting_reviewer_response":
            continue
        last_activity = response_state.get("anchor_timestamp")
        anchor_reason = response_state.get("reason") if isinstance(response_state.get("reason"), str) else None

        if not last_activity:
            continue

        try:
            last_activity_dt = bot.datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        days_since_activity = (now - last_activity_dt).days

        if days_since_activity < bot.REVIEW_DEADLINE_DAYS:
            continue

        transition_warning_sent = review_data.get("transition_warning_sent")
        if transition_warning_sent:
            try:
                warning_dt = bot.datetime.fromisoformat(transition_warning_sent.replace("Z", "+00:00"))
                days_since_warning = (now - warning_dt).days

                if days_since_warning >= bot.TRANSITION_PERIOD_DAYS:
                    overdue.append(
                        {
                            "issue_number": issue_number,
                            "reviewer": current_reviewer,
                            "days_overdue": days_since_activity,
                            "days_since_warning": days_since_warning,
                            "needs_warning": False,
                            "needs_transition": True,
                            "anchor_reason": anchor_reason,
                            "anchor_timestamp": last_activity,
                        }
                    )
            except (ValueError, AttributeError):
                pass
        else:
            overdue.append(
                {
                    "issue_number": issue_number,
                    "reviewer": current_reviewer,
                    "days_overdue": days_since_activity - bot.REVIEW_DEADLINE_DAYS,
                    "days_since_warning": 0,
                    "needs_warning": True,
                    "needs_transition": False,
                    "anchor_reason": anchor_reason,
                    "anchor_timestamp": last_activity,
                }
            )

    return overdue


def find_existing_transition_notice_result(bot, issue_number: int, transition_warning_sent: str | None, reviewer: str | None = None) -> dict[str, object]:
    if not isinstance(transition_warning_sent, str) or not transition_warning_sent:
        return {"status": "missing"}
    return _find_existing_marker_comment(
        bot,
        issue_number,
        f"<!-- {TRANSITION_NOTICE_MARKER_PREFIX} issue={issue_number} reviewer={reviewer or ''} -->",
        authors=_TRANSITION_NOTICE_AUTHORS,
        not_before=transition_warning_sent,
    )


def backfill_transition_notice_if_present(bot, state: dict, issue_number: int) -> bool:
    issue_key = str(issue_number)
    active_reviews = state.get("active_reviews")
    if not isinstance(active_reviews, dict):
        return False
    review_data = active_reviews.get(issue_key)
    if not isinstance(review_data, dict):
        return False
    if review_data.get("transition_notice_sent_at"):
        return False
    existing_notice = find_existing_transition_notice_result(
        bot,
        issue_number,
        review_data.get("transition_warning_sent"),
        review_data.get("current_reviewer"),
    )
    if existing_notice.get("status") == "unavailable":
        if existing_notice.get("failure_kind") in {"unauthorized", "forbidden"}:
            raise RuntimeError(
                f"Permission denied reading transition dedupe comments for #{issue_number} (status {existing_notice.get('status_code')})."
            )
        return _record_transport_failure(
            bot,
            review_data,
            issue_number,
            phase="transition_dedupe_read",
            result=bot.GitHubApiResult(
                existing_notice.get("status_code"),
                None,
                {},
                "",
                False,
                existing_notice.get("failure_kind"),
                existing_notice.get("retry_attempts", 0),
                None,
            ),
        )
    changed = _clear_transport_failure(bot, review_data, issue_number, phase="transition_dedupe_read")
    timestamp = existing_notice.get("timestamp") if existing_notice.get("status") == "found" else None
    if not isinstance(timestamp, str) or not timestamp:
        return changed
    review_data["transition_notice_sent_at"] = timestamp
    bot.collect_touched_item(issue_number)
    return True


def handle_overdue_review_warning(
    bot,
    state: dict,
    issue_number: int,
    reviewer: str,
    *,
    anchor_reason: str | None = None,
    anchor_timestamp: str | None = None,
) -> bool:
    """Post a warning comment and record that we've warned the reviewer."""
    issue_key = str(issue_number)

    if "active_reviews" not in state or issue_key not in state["active_reviews"]:
        return False

    review_data = state["active_reviews"][issue_key]
    if not isinstance(review_data, dict):
        return False
    existing_warning = _warning_scan_result(bot, issue_number, reviewer, anchor_timestamp)
    if existing_warning.get("status") == "unavailable":
        if existing_warning.get("failure_kind") in {"unauthorized", "forbidden"}:
            raise RuntimeError(
                f"Permission denied reading warning dedupe comments for #{issue_number} (status {existing_warning.get('status_code')})."
            )
        return _record_transport_failure(
            bot,
            review_data,
            issue_number,
            phase="warning_dedupe_read",
            result=bot.GitHubApiResult(
                existing_warning.get("status_code"),
                None,
                {},
                "",
                False,
                existing_warning.get("failure_kind"),
                existing_warning.get("retry_attempts", 0),
                None,
            ),
        )
    changed = _clear_transport_failure(bot, review_data, issue_number, phase="warning_dedupe_read")
    if existing_warning.get("status") == "found":
        review_data["transition_warning_sent"] = existing_warning.get("timestamp")
        bot.collect_touched_item(issue_number)
        return True

    warning_message = f"""{_warning_marker(issue_number, reviewer, anchor_timestamp)}

⚠️ **Review Reminder**

{_warning_anchor_sentence(bot, reviewer, anchor_reason)}

**Please take one of the following actions:**

1. **Begin your review** - Post a comment with your feedback
2. **Pass the review** - Use `{bot.BOT_MENTION} /pass [reason]` to assign the next reviewer
3. **Step away temporarily** - Use `{bot.BOT_MENTION} /away YYYY-MM-DD [reason]` if you need time off

If no action is taken within {bot.TRANSITION_PERIOD_DAYS} days, you may be transitioned from Producer to Observer status per our [contribution guidelines](CONTRIBUTING.md#review-deadlines).

_Life happens! If you're dealing with something, just let us know._"""

    post_result = bot.github.post_comment_result(issue_number, warning_message)
    if not post_result.ok:
        if post_result.failure_kind in {"unauthorized", "forbidden"}:
            raise RuntimeError(
                f"Permission denied posting overdue warning for #{issue_number} (status {post_result.status_code})."
            )
        if (
            post_result.failure_kind in {"invalid_payload", "server_error", "transport_error", "rate_limited"}
            or (post_result.status_code is not None and post_result.status_code < 400)
        ):
            existing_warning = _warning_scan_result(bot, issue_number, reviewer, anchor_timestamp)
            if existing_warning.get("status") == "found":
                review_data["transition_warning_sent"] = existing_warning.get("timestamp")
                _clear_transport_failure(bot, review_data, issue_number, phase="warning_post")
                bot.collect_touched_item(issue_number)
                return True
        changed = _record_transport_failure(bot, review_data, issue_number, phase="warning_post", result=post_result)
        return changed or changed

    changed = _clear_transport_failure(bot, review_data, issue_number, phase="warning_post") or changed

    now = bot.datetime.now(bot.timezone.utc).isoformat()
    review_data["transition_warning_sent"] = now
    bot.collect_touched_item(issue_number)

    _log(bot, "info", f"Posted overdue warning for #{issue_number} to @{reviewer}", issue_number=issue_number, reviewer=reviewer)
    return True
