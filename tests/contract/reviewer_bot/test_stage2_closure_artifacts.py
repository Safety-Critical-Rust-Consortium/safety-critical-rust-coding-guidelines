import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _load_fixture(name: str) -> dict:
    return json.loads(Path("tests/fixtures/workflow_contracts", name).read_text(encoding="utf-8"))


def _transition_notice_gate_ready(payload: dict, expected_ref: str) -> bool:
    return (
        payload["artifact_id"] == "transition-notice-fallback-closure"
        and payload["evaluated_repo"] == "rustfoundation/safety-critical-rust-coding-guidelines"
        and payload["evaluated_ref"] == expected_ref
        and payload["closure_ready"] is True
        and payload["remaining_transition_due_without_notice"] == []
    )


def _deferred_payload_gate_ready(payload: dict, expected_ref: str) -> bool:
    return (
        payload["artifact_id"] == "deferred-payload-legacy-closure"
        and payload["evaluated_repo"] == "rustfoundation/safety-critical-rust-coding-guidelines"
        and payload["evaluated_ref"] == expected_ref
        and payload["closure_ready"] is True
        and payload["retained_workflow_inventory_matches"] is True
        and payload["blocking_workflows"] == []
        and payload["queued_or_in_progress_runs"] == []
        and payload["legacy_artifacts_remaining"] == []
    )


def _stage2_closure_cluster_gate(
    transition_notice_payload: dict,
    deferred_payload: dict,
    *,
    expected_ref: str,
) -> bool:
    return _transition_notice_gate_ready(transition_notice_payload, expected_ref) and _deferred_payload_gate_ready(
        deferred_payload, expected_ref
    )


@pytest.mark.parametrize(
    ("fixture_name", "expected_ready"),
    [
        ("stage2_transition_notice_fallback_closure_green.json", True),
        ("stage2_transition_notice_fallback_closure_blocked.json", False),
    ],
)
def test_transition_notice_closure_fixture_schema_and_gate_rule(fixture_name, expected_ready):
    payload = _load_fixture(fixture_name)

    assert set(payload) == {
        "artifact_id",
        "generated_at",
        "evaluated_repo",
        "evaluated_ref",
        "state_issue_number",
        "closure_ready",
        "active_reviews_scanned",
        "resolved_by_marker_backfill",
        "resolved_by_legacy_prose_backfill",
        "resolved_by_new_marker_notice",
        "remaining_transition_due_without_notice",
        "commands_run",
    }
    assert payload["closure_ready"] is expected_ready
    assert payload["closure_ready"] == (payload["remaining_transition_due_without_notice"] == [])


@pytest.mark.parametrize(
    ("fixture_name", "expected_ready"),
    [
        ("stage2_deferred_payload_legacy_closure_green.json", True),
        ("stage2_deferred_payload_legacy_closure_blocked.json", False),
    ],
)
def test_deferred_payload_closure_fixture_schema_and_gate_rule(fixture_name, expected_ready):
    payload = _load_fixture(fixture_name)

    assert set(payload) == {
        "artifact_id",
        "generated_at",
        "evaluated_repo",
        "evaluated_ref",
        "closure_ready",
        "retained_workflow_inventory_matches",
        "blocking_workflows",
        "queued_or_in_progress_runs",
        "legacy_artifacts_remaining",
        "control_plane_actions_applied",
        "commands_run",
    }
    assert payload["closure_ready"] is expected_ready
    assert payload["closure_ready"] == (
        payload["retained_workflow_inventory_matches"]
        and payload["blocking_workflows"] == []
        and payload["queued_or_in_progress_runs"] == []
        and payload["legacy_artifacts_remaining"] == []
    )


def test_stage2_closure_artifacts_reject_stale_attempt_refs():
    transition_notice_payload = _load_fixture("stage2_transition_notice_fallback_closure_green.json")
    deferred_payload = _load_fixture("stage2_deferred_payload_legacy_closure_green.json")

    assert _transition_notice_gate_ready(
        transition_notice_payload,
        "0000000000000000000000000000000000000000",
    ) is False
    assert _deferred_payload_gate_ready(
        deferred_payload,
        "0000000000000000000000000000000000000000",
    ) is False


def test_stage2_closure_cluster_gate_requires_both_current_attempt_green_artifacts():
    transition_notice_payload = _load_fixture("stage2_transition_notice_fallback_closure_green.json")
    deferred_payload = _load_fixture("stage2_deferred_payload_legacy_closure_green.json")
    blocked_transition_notice_payload = _load_fixture(
        "stage2_transition_notice_fallback_closure_blocked.json"
    )
    blocked_deferred_payload = _load_fixture("stage2_deferred_payload_legacy_closure_blocked.json")
    expected_ref = transition_notice_payload["evaluated_ref"]

    assert _stage2_closure_cluster_gate(
        transition_notice_payload,
        deferred_payload,
        expected_ref=expected_ref,
    ) is True
    assert _stage2_closure_cluster_gate(
        blocked_transition_notice_payload,
        deferred_payload,
        expected_ref=expected_ref,
    ) is False
    assert _stage2_closure_cluster_gate(
        transition_notice_payload,
        blocked_deferred_payload,
        expected_ref=expected_ref,
    ) is False
