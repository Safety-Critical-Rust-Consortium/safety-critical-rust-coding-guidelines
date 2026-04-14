"""Issue and PR lifecycle handlers for reviewer-bot."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import assignment_flow
from .config import CODING_GUIDELINE_LABEL, TRANSITION_NOTICE_MARKER_PREFIX
from .review_state import (
    accept_channel_event,
    ensure_review_entry,
    mark_review_complete,
    record_transition_notice_sent,
)
from .reviews import rebuild_pr_approval_state


def _log(bot, level: str, message: str, **fields) -> None:
    bot.logger.event(level, message, **fields)


@dataclass(frozen=True)
class HeadObservationRepairResult:
    changed: bool
    outcome: str
    failure_kind: str | None = None
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.changed


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_epoch(state: dict) -> str:
    return str(state.get("freshness_runtime_epoch", "")).strip() or "legacy_v14"


def _normalize_comment_body(body: str) -> str:
    return "\n".join(line.rstrip() for line in body.replace("\r\n", "\n").split("\n")).strip()


def _semantic_digest(value: str) -> str:
    return hashlib.sha256(_normalize_comment_body(value).encode("utf-8")).hexdigest()


def _write_transition_notice_marker_cutover(bot) -> None:
    config_dir_value = bot.get_config_value("OPENCODE_CONFIG_DIR").strip()
    if not config_dir_value:
        return
    config_dir = Path(config_dir_value)
    artifact_path = config_dir / "reviewer-bot" / "issue-428-reminder-remediation" / "transition-notice-marker-cutover.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(
            {
                "artifact_id": "transition-notice-marker-cutover",
                "completed_at": bot.clock.now().isoformat(),
                "state_issue_number": bot.state_issue_number(),
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def handle_transition_notice(bot, state: dict, issue_number: int, reviewer: str) -> bool:
    from .overdue import (
        _clear_transport_failure,
        _record_transport_failure,
        find_existing_transition_notice_result,
    )

    review_data = ensure_review_entry(state, issue_number, create=True)
    if review_data is None:
        return False
    if review_data.get("transition_notice_sent_at"):
        return False
    existing_notice = find_existing_transition_notice_result(
        bot,
        issue_number,
        review_data.get("transition_warning_sent"),
        reviewer,
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
    if isinstance(timestamp, str) and timestamp:
        record_transition_notice_sent(review_data, timestamp)
        bot.collect_touched_item(issue_number)
        return True
    notice_message = f"""<!-- {TRANSITION_NOTICE_MARKER_PREFIX} issue={issue_number} reviewer={reviewer} -->

🔔 **Transition Period Ended**

@{reviewer}, the {bot.TRANSITION_PERIOD_DAYS}-day transition period has passed without activity on this review.

Per our [contribution guidelines](CONTRIBUTING.md#review-deadlines), this may result in a transition from Producer to Observer status.

You may still continue this review, or use `{bot.BOT_MENTION} /pass`, `{bot.BOT_MENTION} /release`, or `{bot.BOT_MENTION} /away` if you need to step back.

_If you believe this is in error or have extenuating circumstances, please reach out to the subcommittee._"""
    post_result = bot.github.post_comment_result(issue_number, notice_message)
    if not post_result.ok:
        if post_result.failure_kind in {"unauthorized", "forbidden"}:
            raise RuntimeError(
                f"Permission denied posting transition notice for #{issue_number} (status {post_result.status_code})."
            )
        if (
            post_result.failure_kind in {"invalid_payload", "server_error", "transport_error", "rate_limited"}
            or (post_result.status_code is not None and post_result.status_code < 400)
        ):
            existing_notice = find_existing_transition_notice_result(
                bot,
                issue_number,
                review_data.get("transition_warning_sent"),
                reviewer,
            )
            timestamp = existing_notice.get("timestamp") if existing_notice.get("status") == "found" else None
            if isinstance(timestamp, str) and timestamp:
                record_transition_notice_sent(review_data, timestamp)
                _clear_transport_failure(bot, review_data, issue_number, phase="transition_post")
                bot.collect_touched_item(issue_number)
                return True
        return _record_transport_failure(bot, review_data, issue_number, phase="transition_post", result=post_result)
    changed = _clear_transport_failure(bot, review_data, issue_number, phase="transition_post") or changed
    _write_transition_notice_marker_cutover(bot)
    record_transition_notice_sent(
        review_data,
        bot.datetime.now(bot.timezone.utc).isoformat(),
    )
    bot.collect_touched_item(issue_number)
    return True


def _tracked_review_issue(bot, labels: list[str]) -> bool:
    return any(label in bot.REVIEW_LABELS for label in labels)


def _reconcile_lifecycle_reviewer_authority(
    bot,
    state: dict,
    request,
    *,
    assignment_method: str,
    allow_auto_assign: bool,
) -> bool:
    issue_number = request.issue_number
    if not issue_number:
        return False
    bot.collect_touched_item(issue_number)
    labels = list(request.issue_labels)
    if not _tracked_review_issue(bot, labels):
        return False
    current_assignees = bot.github.get_issue_assignees(issue_number)
    if current_assignees is None:
        raise RuntimeError(f"Unable to determine assignees for #{issue_number}")
    cycle_started_at = request.event_created_at or request.updated_at or _now_iso()
    if len(current_assignees) == 1:
        reviewer = current_assignees[0]
        if request.issue_author and reviewer.lower() == request.issue_author.lower():
            return assignment_flow.clear_reviewer_authority(bot, state, issue_number, reason="self_review_not_allowed")
        result = assignment_flow.confirm_reviewer_assignment(
            bot,
            state,
            request,
            reviewer=reviewer,
            assignment_method=assignment_method,
            cycle_started_at=cycle_started_at,
            current_assignees=current_assignees,
            record_assignment=False,
            emit_guidance=False,
            emit_failure_comment=False,
            pr_head_sha=request.pr_head_sha,
        )
        return bool(
            result.get("confirmed")
            or result.get("cleared_current_reviewer")
            or result.get("diagnostic_changed")
        )
    if len(current_assignees) > 1:
        return assignment_flow.clear_reviewer_authority(bot, state, issue_number, reason="multiple_live_assignees")
    if not allow_auto_assign:
        return assignment_flow.clear_reviewer_authority(bot, state, issue_number, reason="no_live_assignees")
    reviewer = bot.adapters.queue.get_next_reviewer(
        state,
        skip_usernames={request.issue_author} if request.issue_author else set(),
    )
    if not reviewer:
        bot.github.post_comment(
            issue_number,
            f"⚠️ No reviewers available in the queue. Please use `{bot.BOT_MENTION} /sync-members` to update the queue.",
        )
        return False
    result = assignment_flow.confirm_reviewer_assignment(
        bot,
        state,
        request,
        reviewer=reviewer,
        assignment_method="round-robin",
        cycle_started_at=cycle_started_at,
        current_assignees=current_assignees,
        record_assignment=True,
        emit_guidance=True,
        emit_failure_comment=True,
        pr_head_sha=request.pr_head_sha,
    )
    return bool(
        result.get("confirmed")
        or result.get("cleared_current_reviewer")
        or result.get("diagnostic_changed")
    )


def _clear_completion(review_data: dict) -> bool:
    changed = False
    if review_data.get("review_completed_at") is not None:
        review_data["review_completed_at"] = None
        changed = True
    if review_data.get("review_completed_by") is not None:
        review_data["review_completed_by"] = None
        changed = True
    if review_data.get("review_completion_source") is not None:
        review_data["review_completion_source"] = None
        changed = True
    if review_data.get("current_cycle_completion"):
        review_data["current_cycle_completion"] = {}
        changed = True
    return changed


def handle_issue_or_pr_opened(bot, state: dict) -> bool:
    bot.assert_lock_held("handle_issue_or_pr_opened")
    from .event_inputs import build_issue_lifecycle_request

    request = build_issue_lifecycle_request(bot)
    issue_key = str(request.issue_number)
    tracked_reviewer = None
    if isinstance(state.get("active_reviews"), dict) and issue_key in state["active_reviews"]:
        review_data = state["active_reviews"][issue_key]
        if isinstance(review_data, dict):
            tracked_reviewer = review_data.get("current_reviewer")
    if tracked_reviewer:
        return False
    return _reconcile_lifecycle_reviewer_authority(
        bot,
        state,
        request,
        assignment_method="lifecycle-opened",
        allow_auto_assign=True,
    )


def handle_issue_edited_event(bot, state: dict) -> bool:
    bot.assert_lock_held("handle_issue_edited_event")
    from .event_inputs import build_issue_lifecycle_request

    request = build_issue_lifecycle_request(bot)
    if request.is_pull_request:
        return False
    issue_number = request.issue_number
    if not issue_number:
        return False
    bot.collect_touched_item(issue_number)
    issue_author = request.issue_author
    editor = request.sender_login or issue_author
    if not issue_author or editor.lower() != issue_author.lower():
        return False
    review_data = ensure_review_entry(state, issue_number)
    if review_data is None:
        return False
    updated_at = request.updated_at or _now_iso()
    current_title = request.issue_title
    current_body = request.issue_body
    previous_title = request.previous_title
    previous_body = request.previous_body
    title_changed = _normalize_comment_body(current_title) != _normalize_comment_body(previous_title)
    body_changed = _normalize_comment_body(current_body) != _normalize_comment_body(previous_body)
    if not title_changed and not body_changed:
        return False
    if title_changed and body_changed:
        semantic_key = f"issues_edit_title_body:{issue_number}:{_semantic_digest(current_title)}:{_semantic_digest(current_body)}"
    elif title_changed:
        semantic_key = f"issues_edit_title:{issue_number}:{_semantic_digest(current_title)}"
    else:
        semantic_key = f"issues_edit_body:{issue_number}:{_semantic_digest(current_body)}"
    return accept_channel_event(
        review_data,
        "contributor_comment",
        semantic_key=semantic_key,
        timestamp=updated_at,
        actor=issue_author,
        source_precedence=0,
    )


def handle_labeled_event(bot, state: dict) -> bool:
    bot.assert_lock_held("handle_labeled_event")
    from .event_inputs import build_issue_lifecycle_request

    request = build_issue_lifecycle_request(bot)
    issue_number = request.issue_number
    if not issue_number:
        return False
    label_name = request.label_name
    is_pr = request.is_pull_request
    bot.collect_touched_item(issue_number)
    if label_name == "sign-off: create pr":
        if is_pr:
            return False
        if CODING_GUIDELINE_LABEL not in set(request.issue_labels):
            return False
        review_data = ensure_review_entry(state, issue_number)
        reviewer = review_data.get("current_reviewer") if review_data else None
        return mark_review_complete(state, issue_number, reviewer, "issue_label: sign-off: create pr")
    if label_name not in bot.REVIEW_LABELS:
        return False
    return handle_issue_or_pr_opened(bot, state)


def handle_unlabeled_event(bot, state: dict) -> bool:
    bot.assert_lock_held("handle_unlabeled_event")
    from .event_inputs import build_issue_lifecycle_request

    request = build_issue_lifecycle_request(bot)
    if not request.issue_number:
        return False
    bot.collect_touched_item(request.issue_number)
    changed = False
    review_data = ensure_review_entry(state, request.issue_number)
    if (
        request.label_name == "sign-off: create pr"
        and isinstance(review_data, dict)
        and review_data.get("review_completion_source") == "issue_label: sign-off: create pr"
    ):
        changed = _clear_completion(review_data) or changed
    if request.label_name in bot.REVIEW_LABELS and not _tracked_review_issue(bot, list(request.issue_labels)):
        changed = assignment_flow.clear_reviewer_authority(bot, state, request.issue_number, reason="review_label_removed") or changed
    return changed


def handle_assigned_event(bot, state: dict) -> bool:
    bot.assert_lock_held("handle_assigned_event")
    from .event_inputs import build_issue_lifecycle_request

    request = build_issue_lifecycle_request(bot)
    return _reconcile_lifecycle_reviewer_authority(
        bot,
        state,
        request,
        assignment_method="lifecycle-assigned",
        allow_auto_assign=False,
    )


def handle_unassigned_event(bot, state: dict) -> bool:
    bot.assert_lock_held("handle_unassigned_event")
    from .event_inputs import build_issue_lifecycle_request

    request = build_issue_lifecycle_request(bot)
    return _reconcile_lifecycle_reviewer_authority(
        bot,
        state,
        request,
        assignment_method="lifecycle-unassigned",
        allow_auto_assign=False,
    )


def handle_reopened_event(bot, state: dict) -> bool:
    bot.assert_lock_held("handle_reopened_event")
    from .event_inputs import build_issue_lifecycle_request

    request = build_issue_lifecycle_request(bot)
    changed = _reconcile_lifecycle_reviewer_authority(
        bot,
        state,
        request,
        assignment_method="lifecycle-reopened",
        allow_auto_assign=False,
    )
    review_data = ensure_review_entry(state, request.issue_number)
    if isinstance(review_data, dict) and review_data.get("review_completion_source") != "issue_label: sign-off: create pr":
        changed = _clear_completion(review_data) or changed
    return changed


def handle_pull_request_target_synchronize(bot, state: dict) -> bool:
    bot.assert_lock_held("handle_pull_request_target_synchronize")
    from .event_inputs import build_pull_request_sync_request

    if _runtime_epoch(state) != "freshness_v15":
        _log(bot, "info", "V18 synchronize repair safe-noop before epoch flip")
        return False
    request = build_pull_request_sync_request(bot)
    issue_number = request.issue_number
    if not issue_number:
        return False
    review_data = ensure_review_entry(state, issue_number)
    if review_data is None or not review_data.get("current_reviewer"):
        return False
    head_sha = request.head_sha
    if not head_sha:
        raise RuntimeError("Missing PR_HEAD_SHA for synchronize event")
    if not request.event_created_at:
        raise RuntimeError("Missing EVENT_CREATED_AT for synchronize event")
    bot.collect_touched_item(issue_number)
    previous_head_sha = review_data.get("active_head_sha")
    previous_completion = deepcopy(review_data.get("current_cycle_completion"))
    previous_write_approval = deepcopy(review_data.get("current_cycle_write_approval"))
    previous_review_completed_at = review_data.get("review_completed_at")
    previous_review_completed_by = review_data.get("review_completed_by")
    previous_review_completion_source = review_data.get("review_completion_source")
    review_data["active_head_sha"] = head_sha
    timestamp = request.event_created_at
    changed = accept_channel_event(
        review_data,
        "contributor_revision",
        semantic_key=f"pull_request_sync:{issue_number}:{head_sha}",
        timestamp=timestamp,
        reviewed_head_sha=head_sha,
        source_precedence=1,
    )
    rebuild_pr_approval_state(bot, issue_number, review_data)
    approval_changed = (
        previous_completion != review_data.get("current_cycle_completion")
        or previous_write_approval != review_data.get("current_cycle_write_approval")
        or previous_review_completed_at != review_data.get("review_completed_at")
        or previous_review_completed_by != review_data.get("review_completed_by")
        or previous_review_completion_source != review_data.get("review_completion_source")
    )
    return changed or previous_head_sha != review_data.get("active_head_sha") or approval_changed


def maybe_record_head_observation_repair(bot, issue_number: int, review_data: dict) -> HeadObservationRepairResult:
    try:
        response = bot.github_api_request("GET", f"pulls/{issue_number}", retry_policy="idempotent_read")
    except SystemExit:
        payload = bot.github_api("GET", f"pulls/{issue_number}")
        if not isinstance(payload, dict):
            return HeadObservationRepairResult(
                changed=False,
                outcome="skipped_unavailable",
                failure_kind="unavailable",
                reason="pull_request_unavailable",
            )
        response = bot.GitHubApiResult(
            status_code=200,
            payload=payload,
            headers={},
            text="",
            ok=True,
            failure_kind=None,
            retry_attempts=0,
            transport_error=None,
        )
    if not response.ok:
        if response.failure_kind == "not_found":
            return HeadObservationRepairResult(
                changed=False,
                outcome="skipped_not_found",
                failure_kind=response.failure_kind,
                reason=f"pull_request_{response.failure_kind}",
            )
        return HeadObservationRepairResult(
            changed=False,
            outcome="skipped_unavailable",
            failure_kind=response.failure_kind,
            reason="pull_request_unavailable",
        )
    pull_request = response.payload
    if not isinstance(pull_request, dict):
        return HeadObservationRepairResult(
            changed=False,
            outcome="invalid_live_payload",
            failure_kind="invalid_payload",
            reason="pull_request_payload_invalid",
        )
    if str(pull_request.get("state", "")).lower() != "open":
        return HeadObservationRepairResult(changed=False, outcome="skipped_not_open")
    head = pull_request.get("head")
    head_sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(head_sha, str) or not head_sha.strip():
        return HeadObservationRepairResult(
            changed=False,
            outcome="invalid_live_payload",
            failure_kind="invalid_payload",
            reason="pull_request_head_unavailable",
        )
    head_sha = head_sha.strip()
    current_head = review_data.get("active_head_sha")
    if current_head == head_sha:
        return HeadObservationRepairResult(changed=False, outcome="unchanged")
    contributor_revision = review_data.get("contributor_revision", {}).get("accepted")
    if isinstance(contributor_revision, dict) and contributor_revision.get("reviewed_head_sha") == head_sha:
        review_data["active_head_sha"] = head_sha
        return HeadObservationRepairResult(changed=True, outcome="changed")
    changed = accept_channel_event(
        review_data,
        "contributor_revision",
        semantic_key=f"pull_request_head_observed:{issue_number}:{head_sha}",
        timestamp=_now_iso(),
        reviewed_head_sha=head_sha,
        source_precedence=0,
    )
    review_data["active_head_sha"] = head_sha
    review_data["current_cycle_completion"] = {}
    review_data["current_cycle_write_approval"] = {}
    review_data["review_completed_at"] = None
    review_data["review_completed_by"] = None
    review_data["review_completion_source"] = None
    return HeadObservationRepairResult(changed=changed, outcome="changed" if changed else "unchanged")


def handle_closed_event(bot, state: dict) -> bool:
    bot.assert_lock_held("handle_closed_event")
    from .event_inputs import build_issue_lifecycle_request

    request = build_issue_lifecycle_request(bot)
    issue_number = request.issue_number
    if not issue_number:
        return False
    bot.collect_touched_item(issue_number)
    issue_key = str(issue_number)
    if isinstance(state.get("active_reviews"), dict) and issue_key in state["active_reviews"]:
        del state["active_reviews"][issue_key]
        return True
    return False
