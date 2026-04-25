import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

pytestmark = pytest.mark.contract

from scripts.reviewer_bot_lib import reconcile_payloads


def _load_fixture_payload(relative_path: str) -> dict:
    data = json.loads(Path(relative_path).read_text(encoding="utf-8"))
    return data["payload"]


def _load_workflow_job(relative_path: str) -> dict:
    workflow = yaml.safe_load(Path(relative_path).read_text(encoding="utf-8"))
    job_name = "route-pr-comment" if relative_path.endswith("reviewer-bot-pr-comment-router.yml") else "observer"
    return workflow["jobs"][job_name]


def _payload_and_upload_steps(job: dict) -> tuple[dict, dict]:
    build_step = next(step for step in job["steps"] if step.get("env", {}).get("PAYLOAD_PATH", "").endswith(".json"))
    upload_step = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/upload-artifact@"))
    return build_step, upload_step


def _extract_python_heredoc(run_script: str) -> str:
    start = "python - <<'PY'\n"
    if start not in run_script:
        raise AssertionError("workflow step does not contain a single-quoted Python heredoc")
    body = run_script.split(start, 1)[1]
    return body.rsplit("\nPY", 1)[0]


@pytest.mark.parametrize(
    ("workflow_path",),
    [
        (".github/workflows/reviewer-bot-pr-comment-router.yml",),
        (".github/workflows/reviewer-bot-pr-review-submitted-observer.yml",),
        (".github/workflows/reviewer-bot-pr-review-dismissed-observer.yml",),
        (".github/workflows/reviewer-bot-pr-review-comment-observer.yml",),
    ],
)
def test_observer_workflow_files_upload_exactly_one_json_payload(workflow_path):
    build_step, upload_step = _payload_and_upload_steps(_load_workflow_job(workflow_path))

    assert build_step["env"]["PAYLOAD_PATH"].endswith(".json")
    assert upload_step["with"]["path"] == build_step["env"]["PAYLOAD_PATH"]
    assert isinstance(upload_step["with"]["name"], str) and upload_step["with"]["name"]


@pytest.mark.parametrize(
    ("fixture_path", "expected_event_name", "expected_event_action"),
    [
        ("tests/fixtures/observer_payloads/workflow_pr_comment_deferred.json", "issue_comment", "created"),
        (
            "tests/fixtures/observer_payloads/workflow_pr_review_submitted_deferred.json",
            "pull_request_review",
            "submitted",
        ),
        (
            "tests/fixtures/observer_payloads/workflow_pr_review_dismissed_deferred.json",
            "pull_request_review",
            "dismissed",
        ),
        (
            "tests/fixtures/observer_payloads/workflow_pr_review_comment_deferred.json",
            "pull_request_review_comment",
            "created",
        ),
    ],
)
def test_deferred_payload_fixtures_parse_identity_without_packaging_contracts(
    fixture_path, expected_event_name, expected_event_action
):
    payload = _load_fixture_payload(fixture_path)
    parsed = reconcile_payloads.parse_deferred_context_payload(payload)

    assert parsed.identity.source_event_name == expected_event_name
    assert parsed.identity.source_event_action == expected_event_action
    assert parsed.identity.source_run_id == payload["source_run_id"]
    assert parsed.identity.source_run_attempt == payload["source_run_attempt"]
    assert parsed.raw_payload == payload


def test_deferred_comment_payload_parses_without_artifact_name_field():
    payload = _load_fixture_payload("tests/fixtures/observer_payloads/workflow_pr_comment_deferred.json")
    payload.pop("source_artifact_name", None)

    parsed = reconcile_payloads.parse_deferred_context_payload(payload)

    assert parsed.identity.source_event_name == "issue_comment"


def test_review_comment_workflow_payload_builder_emits_parseable_contract(monkeypatch, tmp_path):
    workflow_path = ".github/workflows/reviewer-bot-pr-review-comment-observer.yml"
    build_step, _ = _payload_and_upload_steps(_load_workflow_job(workflow_path))
    payload_path = tmp_path / "deferred-review-comment.json"
    env_values = {
        "PAYLOAD_PATH": str(payload_path),
        "GITHUB_RUN_ID": "404",
        "GITHUB_RUN_ATTEMPT": "6",
        "COMMENT_BODY": "@guidelines-bot /queue",
        "PR_NUMBER": "42",
        "ISSUE_AUTHOR": "dana",
        "ISSUE_STATE": "open",
        "ISSUE_LABELS": '["coding guideline"]',
        "COMMENT_ID": "701",
        "COMMENT_CREATED_AT": "2026-03-20T21:00:00Z",
        "COMMENT_AUTHOR": "reviewer2",
        "COMMENT_AUTHOR_ID": "7004",
        "COMMENT_USER_TYPE": "User",
        "COMMENT_COMMIT_ID": "abc123def456",
        "COMMENT_SENDER_TYPE": "User",
        "COMMENT_INSTALLATION_ID": "",
        "COMMENT_PERFORMED_VIA_GITHUB_APP": "false",
    }
    for name, value in env_values.items():
        monkeypatch.setenv(name, value)

    exec(compile(_extract_python_heredoc(build_step["run"]), workflow_path, "exec"), {})

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    parsed = reconcile_payloads.parse_deferred_context_payload(payload)
    fixture_payload = _load_fixture_payload("tests/fixtures/observer_payloads/workflow_pr_review_comment_deferred.json")

    assert payload == fixture_payload
    assert parsed.source_commit_id == "abc123def456"


def test_dismissed_review_payload_does_not_fabricate_source_dismissal_time_contract():
    payload = _load_fixture_payload("tests/fixtures/observer_payloads/workflow_pr_review_dismissed_deferred.json")
    matrix = json.loads(Path("tests/fixtures/workflow_contracts/observer_payload_contract_matrix.json").read_text(encoding="utf-8"))
    contract = next(item for item in matrix["payload_contracts"] if item["payload_kind"] == "deferred_review_dismissed")

    assert "source_dismissed_at" not in contract["carried_edge_fields"]
    assert "source_dismissed_at" not in payload


@pytest.mark.parametrize(
    ("fixture_path", "workflow_path"),
    [
        (
            "tests/fixtures/observer_payloads/workflow_pr_comment_deferred.json",
            ".github/workflows/reviewer-bot-pr-comment-router.yml",
        ),
        (
            "tests/fixtures/observer_payloads/workflow_pr_review_submitted_deferred.json",
            ".github/workflows/reviewer-bot-pr-review-submitted-observer.yml",
        ),
        (
            "tests/fixtures/observer_payloads/workflow_pr_review_dismissed_deferred.json",
            ".github/workflows/reviewer-bot-pr-review-dismissed-observer.yml",
        ),
        (
            "tests/fixtures/observer_payloads/workflow_pr_review_comment_deferred.json",
            ".github/workflows/reviewer-bot-pr-review-comment-observer.yml",
        ),
    ],
)
def test_deferred_payload_fixtures_do_not_require_exact_artifact_name_helpers(
    fixture_path, workflow_path
):
    payload = _load_fixture_payload(fixture_path)
    job = _load_workflow_job(workflow_path)
    build_step, upload_step = _payload_and_upload_steps(job)

    payload_without_artifact_name = dict(payload)
    payload_without_artifact_name.pop("source_artifact_name", None)

    parsed = reconcile_payloads.parse_deferred_context_payload(payload_without_artifact_name)

    assert parsed.identity.source_run_id == payload["source_run_id"]
    assert parsed.identity.source_run_attempt == payload["source_run_attempt"]
    assert isinstance(upload_step["with"]["name"], str) and upload_step["with"]["name"]
    assert build_step["env"]["PAYLOAD_PATH"].endswith(".json")
    assert upload_step["with"]["path"].endswith(".json")


def test_validate_workflow_run_artifact_identity_rejects_run_attempt_mismatch(monkeypatch):
    monkeypatch.setenv("WORKFLOW_RUN_TRIGGERING_ID", "1")
    monkeypatch.setenv("WORKFLOW_RUN_TRIGGERING_ATTEMPT", "2")
    monkeypatch.setenv("WORKFLOW_RUN_TRIGGERING_CONCLUSION", "success")
    payload = {
        "payload_kind": "deferred_comment",
        "schema_version": 3,
        "source_event_name": "issue_comment",
        "source_event_action": "created",
        "source_workflow_name": "Reviewer Bot PR Comment Router",
        "source_workflow_file": ".github/workflows/reviewer-bot-pr-comment-router.yml",
        "source_run_id": 1,
        "source_run_attempt": 1,
    }

    bot = SimpleNamespace(get_config_value=lambda name, default="": __import__("os").environ.get(name, default))

    with pytest.raises(RuntimeError, match="run_attempt mismatch"):
        reconcile_payloads.validate_workflow_run_artifact_identity(bot, payload)


def test_validate_workflow_run_artifact_identity_requires_successful_conclusion(monkeypatch):
    monkeypatch.setenv("WORKFLOW_RUN_TRIGGERING_ID", "1")
    monkeypatch.setenv("WORKFLOW_RUN_TRIGGERING_ATTEMPT", "1")
    monkeypatch.setenv("WORKFLOW_RUN_TRIGGERING_CONCLUSION", "failure")
    payload = {
        "payload_kind": "deferred_comment",
        "schema_version": 3,
        "source_event_name": "issue_comment",
        "source_event_action": "created",
        "source_workflow_name": "Reviewer Bot PR Comment Router",
        "source_workflow_file": ".github/workflows/reviewer-bot-pr-comment-router.yml",
        "source_run_id": 1,
        "source_run_attempt": 1,
    }

    bot = SimpleNamespace(get_config_value=lambda name, default="": __import__("os").environ.get(name, default))

    with pytest.raises(RuntimeError, match="did not conclude successfully"):
        reconcile_payloads.validate_workflow_run_artifact_identity(bot, payload)
