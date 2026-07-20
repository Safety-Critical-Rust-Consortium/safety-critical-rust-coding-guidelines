import json
from pathlib import Path

from scripts.reviewer_bot_core import deferred_gap_diagnosis


def _load_matrix() -> dict:
    return json.loads(
        Path("tests/fixtures/equivalence/deferred_gap_diagnosis/vocabulary_matrix.json").read_text(
            encoding="utf-8"
        )
    )


def test_deferred_gap_diagnosis_vocabulary_matrix_exists_and_lists_reason_sets():
    matrix = _load_matrix()

    assert matrix["harness_id"] == "C5a deferred gap diagnosis vocabulary matrix"
    assert matrix["reason_values"] == [
        "artifact_missing",
        "artifact_invalid",
        "observer_state_unknown",
        "reconcile_failed_closed",
    ]
    assert "artifact_scan_unavailable" in matrix["diagnostic_reason_values"]
    assert "exact_artifact_missing" in matrix["diagnostic_reason_values"]


def test_deferred_gap_diagnosis_matrix_freezes_visible_review_diagnostic_categories_and_ownership():
    matrix = _load_matrix()

    assert matrix["visible_review_diagnostic_categories"] == [
        "visible_review_without_replay_artifact",
        "no_diagnostic_recommended",
    ]
    assert matrix["ownership_decision"] == {
        "diagnosis": "classifies",
        "sweeper": "records_diagnostics",
    }


def test_deferred_gap_diagnosis_core_produces_frozen_reason_and_recommendation_outputs():
    run_reason = deferred_gap_diagnosis.observer_run_reason_from_details(
        {"status": "waiting", "conclusion": None, "name": "approval_pending"},
        {"status": "waiting", "conclusion": None, "name": "approval_pending"},
    )
    artifact_reason = deferred_gap_diagnosis.classify_artifact_gap_reason(
        {"artifact_inspection_complete": True},
    )
    diagnostic_payload = deferred_gap_diagnosis.describe_visible_review_submission(
        {"current_reviewer": "alice"},
        {
            "id": 202,
            "submitted_at": "2026-03-25T11:00:00Z",
            "commit_id": "head-1",
            "user": {"login": "alice"},
        },
        "pull_request_review:202",
        current_cycle_boundary=deferred_gap_diagnosis.parse_timestamp("2026-03-17T09:00:00Z"),
    )

    assert run_reason == "awaiting_observer_approval"
    assert artifact_reason == "artifact_missing"
    assert diagnostic_payload == {
        "author": "alice",
        "submitted_at": "2026-03-25T11:00:00Z",
        "commit_id": "head-1",
    }
