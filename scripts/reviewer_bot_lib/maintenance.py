"""Manual maintenance and operator-dispatch handlers for reviewer-bot."""

from __future__ import annotations

import json

import yaml

from . import maintenance_privileged, maintenance_schedule, overdue, reviews
from .event_inputs import build_manual_dispatch_request
from .project_board import (
    preview_board_projection_for_item,
    reviewer_board_preflight,
)

ScheduleHandlerResult = maintenance_schedule.ScheduleHandlerResult
SCHEDULE_LIKE_MANUAL_ACTIONS = frozenset({"check-overdue"})
_now_iso = maintenance_privileged._now_iso
_finalize_schedule_result = maintenance_schedule._finalize_schedule_result
_record_maintenance_repair_marker = maintenance_schedule._record_maintenance_repair_marker
_run_tracked_pr_maintenance = maintenance_schedule._run_tracked_pr_maintenance
repair_missing_reviewer_review_state = maintenance_schedule.repair_missing_reviewer_review_state
maybe_record_head_observation_repair = maintenance_schedule.maybe_record_head_observation_repair
check_overdue_reviews = maintenance_schedule.check_overdue_reviews
handle_overdue_review_warning = maintenance_schedule.handle_overdue_review_warning
backfill_transition_notice_if_present = maintenance_schedule.backfill_transition_notice_if_present
handle_transition_notice = maintenance_schedule.handle_transition_notice
sweep_deferred_gaps = maintenance_schedule.sweep_deferred_gaps


def status_projection_repair_needed(bot, state: dict) -> bool:
    current_epoch = state.get("status_projection_epoch")
    return current_epoch != bot.STATUS_PROJECTION_EPOCH


def collect_status_projection_repair_items(bot, state: dict) -> list[int]:
    return maintenance_schedule.collect_status_projection_repair_items(bot, state)


def _preview_output_base(bot, state: dict, request) -> dict[str, object]:
    if request.issue_number is None or request.issue_number <= 0:
        raise RuntimeError("Preview actions require ISSUE_NUMBER to be set to a positive integer")
    return {
        "schema_version": 1,
        "preview_action": request.action,
        "issue_number": request.issue_number,
        "validation_nonce": request.validation_nonce,
        "head_sha": bot.get_config_value("GITHUB_SHA").strip(),
        "workflow_path": ".github/workflows/reviewer-bot-preview.yml",
        **overdue.evaluate_overdue_review_preview(bot, state, request.issue_number),
        "lock_attempted": False,
        "state_save_attempted": False,
        "tracked_state_mutations_attempted": False,
        "touched_projection_attempted": False,
    }


def _emit_preview_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=False))


def is_schedule_like_manual_action(action: str | None) -> bool:
    return action in SCHEDULE_LIKE_MANUAL_ACTIONS


def handle_manual_dispatch(bot, state: dict) -> bool:
    request = build_manual_dispatch_request(bot)
    if is_schedule_like_manual_action(request.action):
        raise RuntimeError("schedule-like manual action must use handle_manual_dispatch_result")
    return _handle_manual_dispatch_request(bot, state, request)


def handle_scheduled_check_result(bot, state: dict) -> ScheduleHandlerResult:
    return maintenance_schedule.handle_scheduled_check_result(bot, state)


def handle_manual_dispatch_result(bot, state: dict) -> ScheduleHandlerResult:
    request = build_manual_dispatch_request(bot)
    if is_schedule_like_manual_action(request.action):
        return handle_scheduled_check_result(bot, state)
    state_changed = _handle_manual_dispatch_request(bot, state, request)
    return maintenance_schedule._finalize_schedule_result(bot, state_changed)


def _handle_manual_dispatch_request(bot, state: dict, request) -> bool:
    action = request.action
    if action == "show-state":
        print(f"Current state:\n{yaml.dump(state, default_flow_style=False)}")
        return False
    if action == "preview-check-overdue":
        _emit_preview_json(_preview_output_base(bot, state, request))
        return False
    if action == "preview-reviewer-board":
        preflight = reviewer_board_preflight(bot)
        if not preflight.enabled:
            print("Reviewer board preview skipped: reviewer board is disabled.")
            return False
        if not preflight.valid:
            raise RuntimeError(
                "Reviewer board preview preflight failed: " + "; ".join(preflight.errors)
            )

        payload = _preview_output_base(bot, state, request)
        preview = preview_board_projection_for_item(bot, state, request.issue_number)
        desired = preview.desired
        payload["board_attention"] = desired.needs_attention if desired is not None else None
        payload["board_waiting_since"] = desired.waiting_since if desired is not None else None
        _emit_preview_json(payload)
        return False
    bot.assert_lock_held("handle_manual_dispatch")
    if action == "sync-members":
        _, changes = bot.adapters.workflow.sync_members_with_queue(state)
        return bool(changes)
    if action == "repair-review-status-labels":
        for issue_number in reviews.list_open_items_with_status_labels(bot):
            bot.collect_touched_item(issue_number)
        return False
    if action == "execute-pending-privileged-command":
        source_event_key = request.privileged_source_event_key
        if not source_event_key:
            raise RuntimeError("Missing PRIVILEGED_SOURCE_EVENT_KEY for privileged command execution")
        return maintenance_privileged.execute_pending_privileged_command(bot, state, source_event_key)
    return False
