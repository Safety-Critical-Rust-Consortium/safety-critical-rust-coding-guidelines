from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

import yaml


def test_sweeper_repair_workflow_removes_reviewer_board_preview_dispatch():
    data = yaml.safe_load(Path(".github/workflows/reviewer-bot-sweeper-repair.yml").read_text(encoding="utf-8"))
    on_block = data.get("on", data.get(True))
    workflow_dispatch = on_block["workflow_dispatch"]
    action_input = workflow_dispatch["inputs"]["action"]
    assert "preview-reviewer-board" not in action_input["options"]
    issue_number_input = workflow_dispatch["inputs"]["issue_number"]
    assert issue_number_input["required"] is False
    assert issue_number_input["type"] == "string"

def test_sweeper_repair_workflow_retains_reviewer_board_env_wiring_without_dispatch_option():
    workflow_text = Path(".github/workflows/reviewer-bot-sweeper-repair.yml").read_text(encoding="utf-8")
    assert "ISSUE_NUMBER: ${{ github.event.inputs.issue_number }}" in workflow_text
    assert (
        "REVIEWER_BOARD_ENABLED: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.action == 'preview-reviewer-board' && 'true' || 'false' }}"
        in workflow_text
    )
    assert (
        "REVIEWER_BOARD_TOKEN: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.action == 'preview-reviewer-board' && secrets.REVIEWER_BOARD_TOKEN || '' }}"
        in workflow_text
    )


def test_sweeper_repair_workflow_exports_retained_manual_dispatch_env_contract():
    data = yaml.safe_load(Path(".github/workflows/reviewer-bot-sweeper-repair.yml").read_text(encoding="utf-8"))
    on_block = data.get("on", data.get(True))
    action_input = on_block["workflow_dispatch"]["inputs"]["action"]
    workflow_text = Path(".github/workflows/reviewer-bot-sweeper-repair.yml").read_text(encoding="utf-8")

    assert "check-overdue" in action_input["options"]
    assert "repair-review-status-labels" in action_input["options"]
    assert "MANUAL_ACTION: ${{ github.event.inputs.action }}" in workflow_text
    assert "ISSUE_NUMBER: ${{ github.event.inputs.issue_number }}" in workflow_text
