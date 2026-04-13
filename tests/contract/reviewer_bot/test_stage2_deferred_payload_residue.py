import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _load_cases() -> dict:
    return json.loads(
        Path("tests/fixtures/workflow_contracts/deferred_payload_residue_cases.json").read_text(
            encoding="utf-8"
        )
    )


def _simulate_residue_audit(case: dict) -> dict:
    blocking_workflows = []
    queued_or_in_progress_runs = []
    legacy_artifacts_remaining = []
    evaluated_ref = case["evaluated_ref"]

    for workflow in case["workflows"]:
        if workflow["classification"] == "required_retained" and workflow["state"] != "active":
            blocking_workflows.append(
                {
                    "workflow_name": workflow["workflow_name"],
                    "workflow_path": workflow["workflow_path"],
                    "reason": "required_retained_workflow_disabled",
                }
            )
        if workflow["classification"] == "removed_legacy" and workflow["state"] == "active":
            blocking_workflows.append(
                {
                    "workflow_name": workflow["workflow_name"],
                    "workflow_path": workflow["workflow_path"],
                    "reason": "removed_legacy_workflow_still_active",
                }
            )

    for run in case["runs"]:
        if run["status"] not in {"queued", "in_progress"}:
            continue
        if run["classification"] == "removed_legacy":
            reason = "removed_legacy_workflow_run"
        elif run["head_sha"] != evaluated_ref:
            reason = "noncurrent_head_sha"
        else:
            continue
        queued_or_in_progress_runs.append(
            {
                "workflow_name": run["workflow_name"],
                "workflow_path": run["workflow_path"],
                "run_id": run["run_id"],
                "run_attempt": run["run_attempt"],
                "status": run["status"],
                "head_sha": run["head_sha"],
                "reason": reason,
            }
        )

    for artifact in case["artifacts"]:
        if artifact["downloadable"] and artifact["payload_schema_version"] in {1, 2}:
            legacy_artifacts_remaining.append(
                {
                    "workflow_name": artifact["workflow_name"],
                    "workflow_path": artifact["workflow_path"],
                    "run_id": artifact["run_id"],
                    "run_attempt": artifact["run_attempt"],
                    "artifact_id": artifact["artifact_id"],
                    "payload_schema_version": artifact["payload_schema_version"],
                    "payload_kind": artifact["payload_kind"],
                    "artifact_name": artifact["artifact_name"],
                    "payload_filename": artifact["payload_filename"],
                }
            )

    return {
        "retained_workflow_inventory_matches": case["retained_workflow_inventory_matches"],
        "blocking_workflows": blocking_workflows,
        "queued_or_in_progress_runs": queued_or_in_progress_runs,
        "legacy_artifacts_remaining": legacy_artifacts_remaining,
        "closure_ready": case["retained_workflow_inventory_matches"]
        and blocking_workflows == []
        and queued_or_in_progress_runs == []
        and legacy_artifacts_remaining == [],
    }


def _select_deferred_payload(files: list[str]) -> str | None:
    json_files = sorted(path for path in files if path.endswith(".json"))
    if len(json_files) > 1:
        raise RuntimeError(f"Expected at most one deferred payload, found {len(json_files)}")
    if len(json_files) == 1:
        return json_files[0]
    return None


@pytest.mark.parametrize("case", _load_cases()["residue_cases"], ids=lambda case: case["id"])
def test_b5e_residue_cases_are_simulated_locally(case):
    simulated = _simulate_residue_audit(case)

    assert simulated == case["expected"]


@pytest.mark.parametrize(
    "case",
    _load_cases()["artifact_selection_cases"],
    ids=lambda case: case["id"],
)
def test_reconcile_artifact_selection_cases_fail_closed(case):
    if case["expected_multiple"]:
        with pytest.raises(RuntimeError, match="Expected at most one deferred payload"):
            _select_deferred_payload(case["files"])
        return

    assert _select_deferred_payload(case["files"]) == case["expected_selected_path"]


def test_router_zero_artifact_success_is_not_classified_as_residue():
    case = next(case for case in _load_cases()["residue_cases"] if case["id"] == "router_zero_artifact_success")

    simulated = _simulate_residue_audit(case)

    assert simulated["blocking_workflows"] == []
    assert simulated["queued_or_in_progress_runs"] == []
    assert simulated["legacy_artifacts_remaining"] == []
    assert simulated["closure_ready"] is True
