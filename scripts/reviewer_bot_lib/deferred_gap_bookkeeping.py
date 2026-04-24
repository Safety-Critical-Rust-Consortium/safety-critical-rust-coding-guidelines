"""Deferred-gap bookkeeping support shared by reconcile and sweeper."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone


def _sidecars(review_data: dict) -> dict:
    sidecars = review_data.get("sidecars")
    if not isinstance(sidecars, dict):
        sidecars = {}
        review_data["sidecars"] = sidecars
    return sidecars


def _deferred_gaps(review_data: dict) -> dict:
    sidecars = _sidecars(review_data)
    deferred_gaps = sidecars.get("deferred_gaps")
    if not isinstance(deferred_gaps, dict):
        deferred_gaps = {}
        sidecars["deferred_gaps"] = deferred_gaps
    return deferred_gaps


def get_deferred_gaps(review_data: dict) -> dict:
    return _deferred_gaps(review_data)


def _reconciled_source_events(review_data: dict) -> dict:
    sidecars = _sidecars(review_data)
    reconciled = sidecars.get("reconciled_source_events")
    if not isinstance(reconciled, dict):
        reconciled = {}
        sidecars["reconciled_source_events"] = reconciled
    return reconciled


def get_reconciled_source_events(review_data: dict) -> dict:
    return _reconciled_source_events(review_data)


def _observer_discovery_watermarks(review_data: dict) -> dict:
    sidecars = _sidecars(review_data)
    watermarks = sidecars.get("observer_discovery_watermarks")
    if not isinstance(watermarks, dict):
        watermarks = {}
        sidecars["observer_discovery_watermarks"] = watermarks
    return watermarks


def get_observer_discovery_watermarks(review_data: dict) -> dict:
    return _observer_discovery_watermarks(review_data)


def _deferred_gap_keys(review_data: dict) -> list[str]:
    return list(_deferred_gaps(review_data))


def _get_deferred_gap(review_data: dict, source_event_key: str) -> dict:
    gap = _deferred_gaps(review_data).get(source_event_key)
    return gap if isinstance(gap, dict) else {}


def _deferred_gap_reason(review_data: dict, source_event_key: str) -> str | None:
    reason = _get_deferred_gap(review_data, source_event_key).get("reason")
    return reason if isinstance(reason, str) else None


def _now_iso(bot) -> str:
    return bot.clock.now().isoformat()


def _reconciled_at_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_source_event_key(review_data: dict, source_event_key: str, payload: dict | None = None) -> None:
    deferred_gaps = _deferred_gaps(review_data)
    if payload is None:
        payload = {}
    payload["source_event_key"] = source_event_key
    deferred_gaps[source_event_key] = payload


def _clear_source_event_key(review_data: dict, source_event_key: str) -> bool:
    deferred_gaps = _deferred_gaps(review_data)
    if source_event_key in deferred_gaps:
        deferred_gaps.pop(source_event_key, None)
        return True
    return False


def _update_deferred_gap_fields(review_data: dict, source_event_key: str, fields: dict) -> bool:
    deferred_gaps = _deferred_gaps(review_data)
    existing = deferred_gaps.get(source_event_key)
    if not isinstance(existing, dict):
        return False
    previous = deepcopy(existing)
    existing.update(fields)
    return previous != existing


def _mark_reconciled_source_event(
    review_data: dict,
    source_event_key: str,
    *,
    reconciled_at: str | None = None,
) -> bool:
    reconciled = _reconciled_source_events(review_data)
    timestamp = reconciled_at or _reconciled_at_now()
    existing = reconciled.get(source_event_key)
    if isinstance(existing, dict):
        if existing.get("source_event_key") != source_event_key or not existing.get("reconciled_at"):
            existing["source_event_key"] = source_event_key
            existing["reconciled_at"] = timestamp
            return True
        return False
    reconciled[source_event_key] = {
        "source_event_key": source_event_key,
        "reconciled_at": timestamp,
    }
    return True


def _was_reconciled_source_event(review_data: dict, source_event_key: str) -> bool:
    existing = _reconciled_source_events(review_data).get(source_event_key)
    if not isinstance(existing, dict):
        return False
    if existing.get("source_event_key") != source_event_key:
        return False
    reconciled_at = existing.get("reconciled_at")
    return isinstance(reconciled_at, str) and bool(reconciled_at.strip())


def _payload_or_existing(payload: dict, existing: dict, key: str):
    value = payload.get(key)
    return existing.get(key) if value is None else value


def _update_deferred_gap(
    bot,
    review_data: dict,
    payload: dict,
    reason: str,
    diagnostic_summary: str,
    *,
    failure_kind: str | None = None,
) -> bool:
    source_event_key = str(payload.get("source_event_key", ""))
    if not source_event_key:
        return False
    deferred_gaps = _deferred_gaps(review_data)
    existing = deferred_gaps.get(source_event_key, {})
    if not isinstance(existing, dict):
        existing = {}
    previous = deepcopy(existing)
    existing.update(
        {
            "source_event_key": source_event_key,
            "source_event_kind": f"{payload.get('source_event_name')}:{payload.get('source_event_action')}",
            "pr_number": payload.get("pr_number"),
            "reason": reason,
            "source_event_created_at": payload.get("source_created_at") or payload.get("source_submitted_at"),
            "source_run_id": _payload_or_existing(payload, existing, "source_run_id"),
            "source_run_attempt": _payload_or_existing(payload, existing, "source_run_attempt"),
            "source_workflow_file": _payload_or_existing(payload, existing, "source_workflow_file"),
            "source_artifact_name": _payload_or_existing(payload, existing, "source_artifact_name"),
            "first_noted_at": existing.get("first_noted_at") or _now_iso(bot),
            "last_checked_at": _now_iso(bot),
            "operator_action_required": True,
            "diagnostic_summary": diagnostic_summary,
            "failure_kind": failure_kind,
        }
    )
    changed = previous != existing
    deferred_gaps[source_event_key] = existing
    return changed
