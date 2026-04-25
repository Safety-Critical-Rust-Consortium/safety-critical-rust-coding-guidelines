"""Trusted deferred reconcile helpers for reviewer-bot workflow_run processing."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from scripts.reviewer_bot_core import comment_routing_policy, reconcile_replay_policy
from scripts.reviewer_bot_core.comment_routing_policy import (
    ObserverCommentClassification,
)

from . import assignment_flow
from . import deferred_gap_bookkeeping as gap_bookkeeping
from . import reconcile_payloads as _reconcile_payloads
from .comment_application import (
    digest_comment_body,
    process_comment_event,
    record_conversation_freshness,
)
from .comment_routing import classify_comment_payload, classify_issue_comment_actor
from .context import CommentEventRequest
from .event_inputs import (
    InvalidEventInput,
    build_event_context,
    build_replay_comment_event_request,
)
from .reconcile_payloads import (
    DeferredCommentPayload,
    DeferredCommentReplayContext,
    DeferredReviewPayload,
    build_deferred_comment_replay_context,
    build_deferred_review_replay_context,
    parse_deferred_context_payload,
)
from .reconcile_reads import (
    LiveCommentReplayContext,
    ReconcileReadError,
)
from .reconcile_reads import (
    read_live_comment_replay_context as _read_live_comment_replay_context,
)
from .reconcile_reads import (
    read_live_pr_replay_context as _read_live_pr_replay_context,
)
from .reconcile_reads import (
    read_optional_reconcile_object as _read_optional_reconcile_object,
)
from .reconcile_reads import (
    read_reconcile_object as _read_reconcile_object,
)
from .reconcile_reads import (
    read_reconcile_reviews as _read_reconcile_reviews,
)
from .reconcile_reads import (
    resolve_review_dismissal_time as _resolve_review_dismissal_time,
)
from .review_state import (
    accept_channel_event,
    ensure_review_entry,
    record_reviewer_activity,
    refresh_reviewer_review_from_live_preferred_review,
)
from .reviews import rebuild_pr_approval_state_result
from .runtime_protocols import (
    ReconcileRectifyRuntimeContext,
    ReconcileWorkflowRuntimeContext,
)

DeferredArtifactIdentity = _reconcile_payloads.DeferredArtifactIdentity
DeferredReviewReplayContext = _reconcile_payloads.DeferredReviewReplayContext
ParsedWorkflowRunPayload = DeferredReviewPayload | DeferredCommentPayload


@dataclass(frozen=True)
class WorkflowRunHandlerResult:
    state_changed: bool
    touched_items: list[int]


def _log(bot: ReconcileWorkflowRuntimeContext, level: str, message: str, **fields) -> None:
    bot.logger.event(level, message, **fields)


def _read_live_pr_state_for_reconcile(bot: ReconcileWorkflowRuntimeContext, pr_number: int) -> str:
    live_pr = _read_reconcile_object(bot, f"pulls/{pr_number}", label=f"live PR #{pr_number}")
    live_state = live_pr.get("state")
    if not isinstance(live_state, str) or not live_state.strip():
        raise ReconcileReadError(f"live PR #{pr_number} state is invalid", failure_kind="invalid_payload")
    return live_state.strip().lower()


def _now_iso(bot: ReconcileWorkflowRuntimeContext) -> str:
    return bot.clock.now().isoformat()


def _record_review_rebuild(bot: ReconcileRectifyRuntimeContext, state: dict, issue_number: int, review_data: dict) -> bool:
    pull_request = _read_reconcile_object(bot, f"pulls/{issue_number}", label=f"pull request #{issue_number}")
    reviews = _read_reconcile_reviews(bot, issue_number)
    before = {
        "reviewer_review": deepcopy(review_data.get("reviewer_review")),
        "active_head_sha": review_data.get("active_head_sha"),
        "current_cycle_completion": deepcopy(review_data.get("current_cycle_completion")),
        "current_cycle_write_approval": deepcopy(review_data.get("current_cycle_write_approval")),
        "review_completed_at": review_data.get("review_completed_at"),
        "review_completed_by": review_data.get("review_completed_by"),
        "review_completion_source": review_data.get("review_completion_source"),
    }
    refresh_reviewer_review_from_live_preferred_review(
        bot,
        issue_number,
        review_data,
        pull_request=pull_request,
        reviews=reviews,
        actor=review_data.get("current_reviewer"),
    )
    approval_result = rebuild_pr_approval_state_result(
        bot,
        issue_number,
        review_data,
        pull_request=pull_request,
        reviews=reviews,
    )
    if not approval_result.get("ok"):
        raise ReconcileReadError(
            f"Unable to rebuild approval state for PR #{issue_number}: {approval_result.get('reason')}",
            failure_kind=str(approval_result.get("failure_kind") or "unavailable"),
        )
    completion = approval_result["completion"]
    after = {
        "reviewer_review": deepcopy(review_data.get("reviewer_review")),
        "active_head_sha": review_data.get("active_head_sha"),
        "current_cycle_completion": deepcopy(review_data.get("current_cycle_completion")),
        "current_cycle_write_approval": deepcopy(review_data.get("current_cycle_write_approval")),
        "review_completed_at": review_data.get("review_completed_at"),
        "review_completed_by": review_data.get("review_completed_by"),
        "review_completion_source": review_data.get("review_completion_source"),
    }
    return before != after or bool(completion.get("completed"))


def reconcile_active_review_entry(
    bot: ReconcileRectifyRuntimeContext,
    state: dict,
    issue_number: int,
    *,
    require_pull_request_context: bool = True,
    completion_source: str = "rectify:reconcile-pr-review",
) -> tuple[str, bool, bool]:
    review_data = ensure_review_entry(state, issue_number)
    if review_data is None:
        return f"ℹ️ No active review entry exists for #{issue_number}; nothing to rectify.", True, False
    assigned_reviewer = review_data.get("current_reviewer")
    if not assigned_reviewer:
        return f"ℹ️ #{issue_number} has no tracked assigned reviewer; nothing to rectify.", True, False
    if require_pull_request_context and bot.get_config_value("IS_PULL_REQUEST", "false").lower() != "true":
        return f"ℹ️ #{issue_number} is not a pull request in this event context; `/rectify` only reconciles PR reviews.", True, False
    if str(state.get("freshness_runtime_epoch", "")).strip() != "freshness_v15" and bot.get_config_value("IS_PULL_REQUEST", "false").lower() == "true":
        return "ℹ️ PR review freshness rectify is epoch-gated and currently inactive.", True, False
    head_repair_result = bot.adapters.review_state.maybe_record_head_observation_repair(issue_number, review_data)
    state_changed = head_repair_result.changed
    try:
        reviews = _read_reconcile_reviews(bot, issue_number)
    except ReconcileReadError:
        return f"❌ Failed to fetch reviews for PR #{issue_number}; cannot run `/rectify`.", False, False
    messages: list[str] = []
    refreshed, latest_review = refresh_reviewer_review_from_live_preferred_review(
        bot,
        issue_number,
        review_data,
        reviews=reviews,
        actor=assigned_reviewer,
    )
    if latest_review is not None:
        latest_state = str(latest_review.get("state", "")).upper()
        if refreshed:
            state_changed = True
            messages.append(f"latest review by @{assigned_reviewer} is `{latest_state}`")
    if _record_review_rebuild(bot, state, issue_number, review_data):
        state_changed = True
        review_data["review_completion_source"] = completion_source
    if review_data.get("mandatory_approver_required"):
        from scripts.reviewer_bot_core import approval_policy

        escalation_opened_at = bot.parse_iso8601_timestamp(review_data.get("mandatory_approver_pinged_at")) or bot.parse_iso8601_timestamp(review_data.get("mandatory_approver_label_applied_at"))
        triage_approval = approval_policy.find_triage_approval_after(bot, reviews, escalation_opened_at)
        if triage_approval is not None:
            approver, _ = triage_approval
            if bot.satisfy_mandatory_approver_requirement(state, issue_number, approver):
                state_changed = True
                messages.append(f"mandatory triage approval satisfied by @{approver}")
    if state_changed:
        return f"✅ Rectified PR #{issue_number}: {'; '.join(messages) or 'reconciled live review state'}.", True, True
    return f"ℹ️ Rectify checked PR #{issue_number}: {'; '.join(messages) or 'no reconciliation transitions applied'}.", True, False


def handle_rectify_command(
    bot: ReconcileRectifyRuntimeContext,
    state: dict,
    issue_number: int,
    comment_author: str,
    reviewer_authority: dict[str, object] | None = None,
) -> tuple[str, bool, bool]:
    request = type(
        "RectifyReviewerAuthorityRequest",
        (),
        {
            "issue_number": issue_number,
            "is_pull_request": bot.get_config_value("IS_PULL_REQUEST", "false").lower() == "true",
        },
    )()
    reviewer_authority = reviewer_authority or assignment_flow.resolve_reviewer_command_authority(
        bot,
        state,
        request,
        actor=comment_author,
    )
    reviewer_authority = assignment_flow.require_reviewer_command_actor(reviewer_authority, comment_author)
    if reviewer_authority.get("authorized"):
        return reconcile_active_review_entry(bot, state, issue_number)
    return (
        assignment_flow.reviewer_command_authority_failure_message("rectify", reviewer_authority),
        False,
        False,
    )


def _load_deferred_context(bot: ReconcileWorkflowRuntimeContext) -> dict:
    return bot.load_deferred_payload()


def _is_missing_optional_router_payload_error(exc: RuntimeError) -> bool:
    message = str(exc)
    return "Missing DEFERRED_CONTEXT_PATH" in message or "missing artifact" in message


def optional_router_payload_missing(bot: ReconcileWorkflowRuntimeContext, event_context) -> bool:
    if event_context.workflow_artifact_contract != "artifact_optional_router":
        return False
    try:
        _load_deferred_context(bot)
    except RuntimeError as exc:
        if not _is_missing_optional_router_payload_error(exc):
            raise
        return True
    return False


def _classify_deferred_comment_payload(payload: DeferredCommentPayload) -> dict:
    if payload.source_comment_class is not None and payload.source_has_non_command_text is not None:
        return {
            "comment_class": payload.source_comment_class,
            "has_non_command_text": payload.source_has_non_command_text,
            "command_count": 1 if payload.source_comment_class in {"command_only", "command_plus_text"} else 0,
        }
    normalized_body = "\n".join(line.rstrip() for line in payload.comment_body.replace("\r\n", "\n").split("\n")).strip()
    classified = comment_routing_policy.classify_comment_payload(
        "@guidelines-bot",
        normalized_body,
        None,
    )
    return {
        "comment_class": classified.get("comment_class", ObserverCommentClassification.PLAIN_TEXT),
        "has_non_command_text": bool(classified.get("has_non_command_text")),
        "command_count": int(classified.get("command_count", 0)),
    }


def _deferred_comment_body_digest_matches(payload: DeferredCommentPayload, live_body: str) -> bool:
    if payload.source_body_digest is not None:
        return digest_comment_body(live_body) == payload.source_body_digest
    return digest_comment_body(live_body) == digest_comment_body(payload.comment_body)


def _reconcile_deferred_comment(
    bot: ReconcileWorkflowRuntimeContext,
    state: dict,
    review_data: dict,
    context: DeferredCommentReplayContext,
) -> bool:
    payload = context.payload.raw_payload
    comment_id = context.comment_id
    pr_number = context.pr_number
    _read_live_pr_replay_context(bot, pr_number)
    source_freshness_eligible = context.source_freshness_eligible
    source_classified = _classify_deferred_comment_payload(context.payload)

    def replay_request(comment_context: LiveCommentReplayContext | None = None, *, comment_body: str = "") -> CommentEventRequest:
        return build_replay_comment_event_request(
            context.payload,
            live_comment=comment_context,
            comment_body=comment_body,
        )

    def record_artifact_invalid(problem: InvalidEventInput) -> bool:
        return gap_bookkeeping.record_deferred_gap_diagnostic(
            bot,
            review_data,
            payload,
            "artifact_invalid",
            str(problem),
        )

    try:
        live_comment = _read_reconcile_object(bot, context.live_comment_endpoint, label=f"deferred comment {comment_id}")
    except ReconcileReadError as exc:
        decision = reconcile_replay_policy.decide_comment_replay(
            comment_id=comment_id,
            source_comment_class=str(source_classified.get("comment_class", ObserverCommentClassification.PLAIN_TEXT)),
            source_has_non_command_text=bool(source_classified.get("has_non_command_text")),
            source_freshness_eligible=source_freshness_eligible,
            live_comment_found=False,
            live_body_digest_matches=False,
            live_classified=None,
            live_failure_kind=exc.failure_kind,
            runbook_path=bot.REVIEW_FRESHNESS_RUNBOOK_PATH,
        )
        changed = False
        if decision.record_source_freshness:
            try:
                changed = record_conversation_freshness(bot, state, replay_request())
            except InvalidEventInput as exc:
                return record_artifact_invalid(exc)
        gap_changed = gap_bookkeeping.record_deferred_gap_diagnostic(
            bot,
            review_data,
            payload,
            str(decision.failed_closed_reason),
            str(decision.diagnostic_summary),
            failure_kind=decision.failure_kind,
        )
        return changed or gap_changed
    comment_context = _read_live_comment_replay_context(live_comment, payload)
    live_body = live_comment.get("body")
    if not isinstance(live_body, str):
        raise RuntimeError("Live deferred comment body is unavailable")
    live_classified = classify_comment_payload(bot, live_body)
    if not _deferred_comment_body_digest_matches(context.payload, live_body):
        decision = reconcile_replay_policy.decide_comment_replay(
            comment_id=comment_id,
            source_comment_class=str(source_classified.get("comment_class", ObserverCommentClassification.PLAIN_TEXT)),
            source_has_non_command_text=bool(source_classified.get("has_non_command_text")),
            source_freshness_eligible=source_freshness_eligible,
            live_comment_found=True,
            live_body_digest_matches=False,
            live_classified={
                "comment_class": str(live_classified.get("comment_class", "plain_text")),
                "has_non_command_text": bool(live_classified.get("has_non_command_text")),
                "command_count": 1,
            },
            live_failure_kind=None,
            runbook_path=bot.REVIEW_FRESHNESS_RUNBOOK_PATH,
        )
        changed = False
        if decision.record_source_freshness:
            try:
                changed = record_conversation_freshness(bot, state, replay_request(comment_context, comment_body=live_body))
            except InvalidEventInput as exc:
                return record_artifact_invalid(exc)
        gap_changed = gap_bookkeeping.record_deferred_gap_diagnostic(
            bot,
            review_data,
            payload,
            str(decision.failed_closed_reason),
            str(decision.diagnostic_summary),
        )
        return changed or gap_changed
    decision = reconcile_replay_policy.decide_comment_replay(
        comment_id=int(payload["comment_id"]),
        source_comment_class=str(source_classified.get("comment_class", ObserverCommentClassification.PLAIN_TEXT)),
        source_has_non_command_text=bool(source_classified.get("has_non_command_text")),
        source_freshness_eligible=source_freshness_eligible,
        live_comment_found=True,
        live_body_digest_matches=True,
        live_classified=live_classified,
        live_failure_kind=None,
        runbook_path=bot.REVIEW_FRESHNESS_RUNBOOK_PATH,
    )
    changed = False
    if decision.record_source_freshness:
        try:
            changed = record_conversation_freshness(bot, state, replay_request(comment_context, comment_body=live_body)) or changed
        except InvalidEventInput as exc:
            return record_artifact_invalid(exc)
    if decision.failed_closed_reason is not None:
        gap_changed = gap_bookkeeping.record_deferred_gap_diagnostic(
            bot,
            review_data,
            payload,
            decision.failed_closed_reason,
            str(decision.diagnostic_summary),
            failure_kind=decision.failure_kind,
        )
        return changed or gap_changed
    if decision.replay_comment_command:
        try:
            changed = process_comment_event(
                bot,
                state,
                replay_request(comment_context, comment_body=live_body),
                classify_comment_payload=lambda _bot, _body: live_classified,
                classify_issue_comment_actor=classify_issue_comment_actor,
            ) or changed
        except InvalidEventInput as exc:
            return record_artifact_invalid(exc)
    reconciled_changed = False
    if decision.mark_reconciled:
        reconciled_changed = gap_bookkeeping.mark_reconciled_source_event(
            review_data,
            str(payload.get("source_event_key", "")),
            reconciled_at=_now_iso(bot),
        )
        gap_cleared_changed = False
        if decision.clear_gap:
            gap_cleared_changed = gap_bookkeeping.clear_deferred_gap(review_data, str(payload.get("source_event_key", "")))
        return changed or reconciled_changed or gap_cleared_changed


def _handle_issue_comment_workflow_run(
    bot: ReconcileWorkflowRuntimeContext,
    state: dict,
    review_data: dict,
    parsed_payload: DeferredCommentPayload,
) -> bool:
    _reconcile_payloads.validate_triggering_run_identity(bot, parsed_payload.raw_payload)
    context = build_deferred_comment_replay_context(
        parsed_payload,
        expected_event_name="issue_comment",
        live_comment_endpoint=f"issues/comments/{parsed_payload.comment_id}",
    )
    return _reconcile_deferred_comment(bot, state, review_data, context)


def _handle_review_comment_workflow_run(
    bot: ReconcileWorkflowRuntimeContext,
    state: dict,
    review_data: dict,
    parsed_payload: DeferredCommentPayload,
) -> bool:
    _reconcile_payloads.validate_triggering_run_identity(bot, parsed_payload.raw_payload)
    context = build_deferred_comment_replay_context(
        parsed_payload,
        expected_event_name="pull_request_review_comment",
        live_comment_endpoint=f"pulls/comments/{parsed_payload.comment_id}",
    )
    return _reconcile_deferred_comment(bot, state, review_data, context)


def _handle_review_submitted_workflow_run(
    bot: ReconcileWorkflowRuntimeContext,
    state: dict,
    review_data: dict,
    parsed_payload: DeferredReviewPayload,
) -> bool:
    _reconcile_payloads.validate_triggering_run_identity(bot, parsed_payload.raw_payload)
    context = build_deferred_review_replay_context(
        parsed_payload,
        expected_event_action="submitted",
    )
    pr_number = context.pr_number
    source_event_key = context.source_event_key
    review_id = context.review_id
    live_review = _read_optional_reconcile_object(bot, f"pulls/{pr_number}/reviews/{review_id}", label=f"live review #{review_id}")
    _read_reconcile_object(bot, f"pulls/{pr_number}", label=f"live PR #{pr_number}")
    live_commit_id = None
    live_submitted_at = parsed_payload.source_submitted_at
    live_state = parsed_payload.source_review_state
    if isinstance(live_review, dict):
        live_commit_id = live_review.get("commit_id")
        live_submitted_at = live_review.get("submitted_at") or live_submitted_at
        live_state = live_review.get("state") or live_state
    else:
        live_commit_id = parsed_payload.source_commit_id
    actor = context.actor_login
    state_changed = bot.adapters.review_state.maybe_record_head_observation_repair(pr_number, review_data).changed
    decision = reconcile_replay_policy.decide_review_submitted_replay(
        source_event_key=source_event_key,
        actor_login=actor,
        current_reviewer=review_data.get("current_reviewer"),
        live_commit_id=live_commit_id if isinstance(live_commit_id, str) else None,
        live_submitted_at=live_submitted_at if isinstance(live_submitted_at, str) else None,
    )
    if decision.accept_reviewer_review:
        accept_channel_event(
            review_data,
            "reviewer_review",
            semantic_key=source_event_key,
            timestamp=str(decision.replay_timestamp),
            actor=str(decision.actor_login),
            reviewed_head_sha=str(decision.reviewed_head_sha),
            source_precedence=1,
        )
        record_reviewer_activity(review_data, str(decision.replay_timestamp))
        state_changed = True
    if _record_review_rebuild(bot, state, pr_number, review_data):
        state_changed = True
    reconciled_changed = gap_bookkeeping.mark_reconciled_source_event(
        review_data,
        source_event_key,
        reconciled_at=_now_iso(bot),
    )
    gap_cleared_changed = gap_bookkeeping.clear_deferred_gap(review_data, source_event_key)
    return state_changed or reconciled_changed or gap_cleared_changed


def _handle_review_dismissed_workflow_run(
    bot: ReconcileWorkflowRuntimeContext,
    state: dict,
    review_data: dict,
    parsed_payload: DeferredReviewPayload,
) -> bool:
    _reconcile_payloads.validate_triggering_run_identity(bot, parsed_payload.raw_payload)
    context = build_deferred_review_replay_context(
        parsed_payload,
        expected_event_action="dismissed",
    )
    source_event_key = context.source_event_key
    dismissal_time = _resolve_review_dismissal_time(
        bot,
        context.pr_number,
        context.review_id,
        parsed_payload.raw_payload,
    )
    if not dismissal_time.exact:
        return gap_bookkeeping.record_deferred_gap_diagnostic(
            bot,
            review_data,
            parsed_payload.raw_payload,
            "reconcile_failed_closed",
            (
                f"Deferred review dismissal {context.review_id} lacks exact source dismissal time; "
                f"dismissal replay suppressed ({dismissal_time.reason or 'unavailable'}). "
                f"See {bot.REVIEW_FRESHNESS_RUNBOOK_PATH}."
            ),
            failure_kind=dismissal_time.failure_kind,
        )
    decision = reconcile_replay_policy.decide_review_dismissed_replay(
        source_event_key=source_event_key,
        timestamp=str(dismissal_time.timestamp),
    )
    state_changed = False
    if decision.accept_review_dismissal:
        state_changed = accept_channel_event(
            review_data,
            "review_dismissal",
            semantic_key=source_event_key,
            timestamp=str(decision.replay_timestamp),
            dismissal_only=True,
        ) or state_changed
    state_changed = bot.adapters.review_state.maybe_record_head_observation_repair(context.pr_number, review_data).changed or state_changed
    state_changed = _record_review_rebuild(bot, state, context.pr_number, review_data) or state_changed
    reconciled_changed = False
    if decision.mark_reconciled:
        reconciled_changed = gap_bookkeeping.mark_reconciled_source_event(
            review_data,
            source_event_key,
            reconciled_at=_now_iso(bot),
        )
    gap_cleared_changed = False
    if decision.clear_gap:
        gap_cleared_changed = gap_bookkeeping.clear_deferred_gap(review_data, source_event_key)
    return state_changed or reconciled_changed or gap_cleared_changed


_WORKFLOW_RUN_HANDLER_MATRIX: dict[tuple[str, str], tuple[type[DeferredCommentPayload] | type[DeferredReviewPayload], object]] = {
    ("issue_comment", "created"): (DeferredCommentPayload, _handle_issue_comment_workflow_run),
    ("pull_request_review_comment", "created"): (DeferredCommentPayload, _handle_review_comment_workflow_run),
    ("pull_request_review", "submitted"): (DeferredReviewPayload, _handle_review_submitted_workflow_run),
    ("pull_request_review", "dismissed"): (DeferredReviewPayload, _handle_review_dismissed_workflow_run),
}


def _workflow_run_handler_for_payload(parsed_payload: ParsedWorkflowRunPayload):
    entry = _WORKFLOW_RUN_HANDLER_MATRIX.get(
        (
            parsed_payload.identity.source_event_name,
            parsed_payload.identity.source_event_action,
        )
    )
    if entry is None:
        return None
    payload_type, handler = entry
    if not isinstance(parsed_payload, payload_type):
        return None
    return handler


def handle_workflow_run_event_result(bot: ReconcileWorkflowRuntimeContext, state: dict) -> WorkflowRunHandlerResult:
    bot.assert_lock_held("handle_workflow_run_event")
    event_context = build_event_context(bot)
    if event_context.workflow_run_triggering_conclusion != "success":
        raise RuntimeError("workflow_run reconcile requires successful triggering conclusion")
    if str(state.get("freshness_runtime_epoch", "")).strip() != "freshness_v15":
        _log(bot, "info", "V18 workflow_run reconcile safe-noop before epoch flip")
        return WorkflowRunHandlerResult(False, [])

    def _build_result(state_changed: bool, pr_number: int) -> WorkflowRunHandlerResult:
        touched_items = bot.drain_touched_items()
        return WorkflowRunHandlerResult(
            state_changed=state_changed,
            touched_items=touched_items,
        )

    try:
        payload = _load_deferred_context(bot)
    except RuntimeError as exc:
        if event_context.workflow_artifact_contract == "artifact_optional_router" and _is_missing_optional_router_payload_error(exc):
            return WorkflowRunHandlerResult(False, [])
        raise
    parsed_payload = parse_deferred_context_payload(payload)
    pr_number = parsed_payload.pr_number
    if pr_number <= 0:
        raise RuntimeError("Deferred context is missing a valid PR number")
    review_data = ensure_review_entry(state, pr_number)
    if review_data is None:
        _log(
            bot,
            "info",
            f"Ignoring deferred workflow_run for missing active review entry on PR #{pr_number}",
            issue_number=pr_number,
            source_event_key=parsed_payload.identity.source_event_key,
        )
        return WorkflowRunHandlerResult(False, [])
    try:
        live_pr_state = _read_live_pr_state_for_reconcile(bot, pr_number)
        if live_pr_state == "closed":
            _log(
                bot,
                "info",
                f"Ignoring deferred workflow_run for closed PR #{pr_number}",
                issue_number=pr_number,
                source_event_key=parsed_payload.identity.source_event_key,
            )
            return WorkflowRunHandlerResult(False, [])
        if live_pr_state != "open":
            raise ReconcileReadError(
                f"live PR #{pr_number} state is unsupported for replay: {live_pr_state}",
                failure_kind="invalid_payload",
            )
        bot.collect_touched_item(pr_number)
        handler = _workflow_run_handler_for_payload(parsed_payload)
        if handler is None:
            raise RuntimeError("Unsupported deferred workflow_run payload")
        return _build_result(handler(bot, state, review_data, parsed_payload), pr_number)
    except RuntimeError as exc:
        bot.collect_touched_item(pr_number)
        failure_kind = exc.failure_kind if isinstance(exc, ReconcileReadError) else None
        gap_changed = gap_bookkeeping.record_deferred_gap_diagnostic(
            bot,
            review_data,
            payload,
            "reconcile_failed_closed",
            f"{exc} See {bot.REVIEW_FRESHNESS_RUNBOOK_PATH}.",
            failure_kind=failure_kind,
        )
        if gap_changed:
            return _build_result(True, pr_number)
        raise
