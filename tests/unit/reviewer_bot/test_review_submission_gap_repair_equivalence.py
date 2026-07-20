import json
from pathlib import Path

from scripts.reviewer_bot_core import deferred_gap_diagnosis


def _load_matrix() -> dict:
    return json.loads(
        Path("tests/fixtures/equivalence/review_submission_gap_repair/scenario_matrix.json").read_text(
            encoding="utf-8"
        )
    )


def test_h4a_review_submission_gap_matrix_freezes_exact_visible_review_diagnostic_outputs():
    matrix = _load_matrix()

    assert matrix["harness_id"] == "H4a review-submitted gap diagnostic flow equivalence"
    scenario = matrix["scenarios"][0]

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

    assert scenario["expected_reason"] is None
    assert scenario["expected_diagnostic_reason"] is None
    assert scenario["expected_diagnostic_category"] == "visible_review_without_replay_artifact"
    assert diagnostic_payload == scenario["expected_diagnostic_payload"]


def test_h4b_review_submission_gap_diagnostic_flow_moves_to_core_owner():
    matrix = _load_matrix()
    scenario = matrix["scenarios"][0]

    diagnostic = deferred_gap_diagnosis.describe_review_submission_gap_diagnostic(
        {"current_reviewer": "alice"},
        {
            "id": 202,
            "submitted_at": "2026-03-25T11:00:00Z",
            "commit_id": "head-1",
            "user": {"login": "alice"},
        },
        "pull_request_review:202",
        artifact_status="artifact_missing",
        current_cycle_boundary=deferred_gap_diagnosis.parse_timestamp("2026-03-17T09:00:00Z"),
    )
    sweeper_text = Path("scripts/reviewer_bot_lib/sweeper.py").read_text(encoding="utf-8")

    assert diagnostic == {
        "category": scenario["expected_diagnostic_category"],
        "payload": scenario["expected_diagnostic_payload"],
    }
    assert "deferred_gap_diagnosis.describe_review_submission_gap_diagnostic(" in sweeper_text
    assert "artifact_status != \"exact_artifact_match\"" not in sweeper_text
