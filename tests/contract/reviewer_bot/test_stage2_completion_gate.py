import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _base() -> Path:
    config_dir = os.environ.get("OPENCODE_CONFIG_DIR", "").strip()
    if not config_dir:
        pytest.skip("OPENCODE_CONFIG_DIR is required for the local Stage 2 completion gate")
    return Path(config_dir) / "reviewer-bot" / "maintainability-remediation"


def _load(name: str) -> dict:
    return json.loads((_base() / name).read_text(encoding="utf-8"))


def test_stage2_completion_gate_requires_after_b6a_green_matrices():
    rc = _load("rc-green-matrix.json")
    hb = _load("hb-green-matrix.json")

    assert rc["evaluation_checkpoint"] == "after-B6a"
    assert hb["evaluation_checkpoint"] == "after-B6a"
    assert [row["id"] for row in rc["decision_rows"]] == [f"RC{number}" for number in range(1, 24)]
    assert [row["id"] for row in hb["decision_rows"]] == [f"HB{number}" for number in range(1, 10)]
    assert all(row["result"] == "pass" for row in rc["decision_rows"])
    assert all(row["result"] == "pass" for row in hb["decision_rows"])


def test_stage2_completion_gate_requires_setup_and_current_attempt_closure_artifacts():
    base = _base()
    for name in [
        "g0a-proof-map.json",
        "g0b-proof-chokepoint-report.json",
        "g0c-runtime-authority-map.json",
        "g0d-state-lock-subsystem-map.json",
        "g0e-consumer-protocol-map.json",
        "g0f-persisted-record-inventory.json",
        "g0g-request-routing-command-map.json",
        "g0h-observer-owner-matrix.json",
        "g0i-workflow-run-envelope-map.json",
        "g0j-operational-truth-map.json",
    ]:
        payload = _load(name)
        assert payload["gate_closed"] is True, name
        assert payload["blocking_decisions_resolved"] is True, name

    assert (base / "router-cutover.json").exists()
    assert (base / "transition-notice-marker-cutover.json").exists()

    expected_ref = _load("stage1-corrective-stage2-readiness-followup-closure.json")["evaluated_ref"]
    transition_notice = _load("transition-notice-fallback-closure.json")
    deferred_payload = _load("deferred-payload-legacy-closure.json")

    assert transition_notice["closure_ready"] is True
    assert deferred_payload["closure_ready"] is True
    assert transition_notice["evaluated_ref"] == expected_ref
    assert deferred_payload["evaluated_ref"] == expected_ref
