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
    workflow = __import__("yaml").safe_load(Path(workflow_path).read_text(encoding="utf-8"))
    job_name = "route-pr-comment" if workflow_path.endswith("reviewer-bot-pr-comment-router.yml") else "observer"
    build_step = workflow["jobs"][job_name]["steps"][0]
    upload_step = workflow["jobs"][job_name]["steps"][1]

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
    build_step = job["steps"][0]
    upload_step = job["steps"][1]

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
