import json
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.contract

import yaml

from scripts.reviewer_bot_core import comment_routing_policy
from scripts.reviewer_bot_lib.context import PrCommentAdmission


def _load_observer_contract_matrix() -> dict:
    return json.loads(
        Path("tests/fixtures/workflow_contracts/observer_payload_contract_matrix.json").read_text(
            encoding="utf-8"
        )
    )


def _load_fixture_payload(relative_path: str) -> dict:
    data = json.loads(Path(relative_path).read_text(encoding="utf-8"))
    return data["payload"]


def test_issue_comment_direct_workflow_exports_issue_state():
    workflow_text = Path(".github/workflows/reviewer-bot-issue-comment-direct.yml").read_text(
        encoding="utf-8"
    )
    assert "ISSUE_STATE: ${{ github.event.issue.state }}" in workflow_text


def test_issue_comment_direct_workflow_exports_retained_request_inputs():
    workflow_text = Path(".github/workflows/reviewer-bot-issue-comment-direct.yml").read_text(
        encoding="utf-8"
    )
    assert "IS_PULL_REQUEST: 'false'" in workflow_text
    assert "COMMENT_AUTHOR_ID: ${{ github.event.comment.user.id }}" in workflow_text


def test_pr_metadata_workflow_exports_label_name_for_labeled_path():
    workflow_text = Path(".github/workflows/reviewer-bot-pr-metadata.yml").read_text(
        encoding="utf-8"
    )
    assert "LABEL_NAME: ${{ github.event.label.name }}" in workflow_text


def test_issue_lifecycle_workflow_covers_retained_event_matrix():
    workflow = yaml.safe_load(Path(".github/workflows/reviewer-bot-issues.yml").read_text(encoding="utf-8"))
    on_block = workflow.get("on", workflow.get(True))

    assert on_block["issues"]["types"] == [
        "opened",
        "edited",
        "labeled",
        "unlabeled",
        "assigned",
        "unassigned",
        "reopened",
        "closed",
    ]


def test_issue_lifecycle_workflow_exports_retained_request_boundary_fields():
    workflow_text = Path(".github/workflows/reviewer-bot-issues.yml").read_text(encoding="utf-8")

    assert "IS_PULL_REQUEST: 'false'" in workflow_text
    assert "ISSUE_STATE: ${{ github.event.issue.state }}" in workflow_text
    assert "LABEL_NAME: ${{ github.event.label.name }}" in workflow_text
    assert "ISSUE_CREATED_AT: ${{ github.event.issue.created_at }}" in workflow_text
    assert "ISSUE_UPDATED_AT: ${{ github.event.issue.updated_at }}" in workflow_text
    assert "ISSUE_CLOSED_AT: ${{ github.event.issue.closed_at }}" in workflow_text
    assert "EVENT_CREATED_AT: ${{ github.event.issue.updated_at }}" not in workflow_text


def test_pr_metadata_workflow_covers_retained_event_matrix():
    workflow = yaml.safe_load(Path(".github/workflows/reviewer-bot-pr-metadata.yml").read_text(encoding="utf-8"))
    on_block = workflow.get("on", workflow.get(True))

    assert on_block["pull_request_target"]["types"] == [
        "opened",
        "labeled",
        "unlabeled",
        "reopened",
        "closed",
        "synchronize",
    ]


def test_pr_metadata_workflow_exports_raw_timestamp_boundary_fields():
    workflow_text = Path(".github/workflows/reviewer-bot-pr-metadata.yml").read_text(encoding="utf-8")

    assert "PR_CREATED_AT: ${{ github.event.pull_request.created_at }}" in workflow_text
    assert "PR_UPDATED_AT: ${{ github.event.pull_request.updated_at }}" in workflow_text
    assert "PR_CLOSED_AT: ${{ github.event.pull_request.closed_at }}" in workflow_text
    assert "EVENT_CREATED_AT: ${{ github.event.pull_request.updated_at }}" not in workflow_text


@pytest.mark.parametrize(
    "workflow_path",
    [
        ".github/workflows/reviewer-bot-pr-comment-router.yml",
        ".github/workflows/reviewer-bot-issue-comment-direct.yml",
        ".github/workflows/reviewer-bot-pr-review-comment-observer.yml",
    ],
)
def test_comment_workflows_export_performed_via_app_boolean_truth(workflow_path):
    workflow_text = Path(workflow_path).read_text(encoding="utf-8")

    assert "COMMENT_USER_TYPE" in workflow_text
    if workflow_path.endswith(("reviewer-bot-pr-comment-router.yml", "reviewer-bot-issue-comment-direct.yml")):
        assert "COMMENT_AUTHOR_ASSOCIATION" in workflow_text
    assert "COMMENT_SENDER_TYPE" in workflow_text
    assert "COMMENT_INSTALLATION_ID" in workflow_text
    assert "COMMENT_PERFORMED_VIA_GITHUB_APP" in workflow_text
    assert "COMMENT_PERFORMED_VIA_GITHUB_APP: ${{ github.event.comment.performed_via_github_app.id > 0 && 'true' || 'false' }}" in workflow_text
    assert "github.event.comment.performed_via_github_app != null" not in workflow_text
    assert "github.event.comment.performed_via_github_app && 'true' || 'false'" not in workflow_text
    assert "toJson(github.event.comment.performed_via_github_app) != 'null'" not in workflow_text


def test_pr_comment_router_normalizes_performed_via_app_without_raw_truthiness():
    workflow_text = Path(".github/workflows/reviewer-bot-pr-comment-router.yml").read_text(encoding="utf-8")

    assert "def _performed_via_github_app_truth(value):" in workflow_text
    assert "return int(value.get('id') or 0) > 0" in workflow_text
    assert "bool(comment.get('performed_via_github_app'))" not in workflow_text


def _load_pr_comment_router_inline_namespace():
    workflow_text = Path(".github/workflows/reviewer-bot-pr-comment-router.yml").read_text(encoding="utf-8")
    first_def = workflow_text.index("def _classify_issue_comment_actor(")
    start = workflow_text.rfind("\n", 0, first_def) + 1
    end = workflow_text.index("\n\n          performed_via_github_app =", start)
    namespace = {}
    exec(textwrap.dedent(workflow_text[start:end]), namespace)
    return namespace


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        (False, False),
        (True, True),
        ({}, False),
        ({"id": 0}, False),
        ({"id": "0"}, False),
        ({"id": 123}, True),
        ({"id": "123"}, True),
        ("false", False),
    ],
)
def test_pr_comment_router_performed_via_app_helper_executes_source_shape_cases(value, expected):
    workflow_text = Path(".github/workflows/reviewer-bot-pr-comment-router.yml").read_text(encoding="utf-8")
    start = workflow_text.index("def _performed_via_github_app_truth(value):")
    end = workflow_text.index("\n\n          performed_via_github_app =", start)
    namespace = {}
    exec(textwrap.dedent(workflow_text[start:end]), namespace)

    assert namespace["_performed_via_github_app_truth"](value) is expected


@pytest.mark.parametrize(
    ("comment_user_type", "comment_author", "comment_sender_type", "installation_id", "performed_via_app"),
    [
        ("User", "alice", "User", None, False),
        ("Bot", "github-actions[bot]", "Bot", None, False),
        ("User", "dependabot[bot]", "User", None, False),
        ("User", "alice", "Organization", None, False),
        ("User", "alice", "User", "12345", False),
        ("User", "alice", "User", None, True),
        ("User", "", "User", None, False),
    ],
)
def test_pr_comment_router_actor_classifier_matches_core_policy(
    comment_user_type,
    comment_author,
    comment_sender_type,
    installation_id,
    performed_via_app,
):
    namespace = _load_pr_comment_router_inline_namespace()

    request = SimpleNamespace(
        comment_user_type=comment_user_type,
        comment_author=comment_author,
        comment_sender_type=comment_sender_type,
        comment_installation_id=installation_id,
        comment_performed_via_github_app=performed_via_app,
    )

    assert namespace["_classify_issue_comment_actor"](
        comment_user_type,
        comment_author,
        comment_sender_type,
        installation_id,
        performed_via_app,
    ) == comment_routing_policy.classify_issue_comment_actor(request)


@pytest.mark.parametrize(
    "scenario",
    [
        {
            "name": "same_repo_trusted_member",
            "comment_user_type": "User",
            "comment_author": "alice",
            "comment_sender_type": "User",
            "installation_id": None,
            "performed_via_app": False,
            "comment_author_association": "MEMBER",
            "pr_head_full_name": "rustfoundation/safety-critical-rust-coding-guidelines",
            "pr_author": "carol",
            "route_outcome": comment_routing_policy.PrCommentRouterOutcome.TRUSTED_DIRECT,
        },
        {
            "name": "same_repo_untrusted_author_association",
            "comment_user_type": "User",
            "comment_author": "alice",
            "comment_sender_type": "User",
            "installation_id": None,
            "performed_via_app": False,
            "comment_author_association": "contributor",
            "pr_head_full_name": "rustfoundation/safety-critical-rust-coding-guidelines",
            "pr_author": "carol",
            "route_outcome": comment_routing_policy.PrCommentRouterOutcome.TRUSTED_DIRECT,
        },
        {
            "name": "cross_repo_deferred",
            "comment_user_type": "User",
            "comment_author": "alice",
            "comment_sender_type": "User",
            "installation_id": None,
            "performed_via_app": False,
            "comment_author_association": "MEMBER",
            "pr_head_full_name": "fork/example",
            "pr_author": "carol",
            "route_outcome": comment_routing_policy.PrCommentRouterOutcome.TRUSTED_DIRECT,
        },
        {
            "name": "dependabot_pr_author_deferred",
            "comment_user_type": "User",
            "comment_author": "alice",
            "comment_sender_type": "User",
            "installation_id": None,
            "performed_via_app": False,
            "comment_author_association": "OWNER",
            "pr_head_full_name": "rustfoundation/safety-critical-rust-coding-guidelines",
            "pr_author": "dependabot[bot]",
            "route_outcome": comment_routing_policy.PrCommentRouterOutcome.TRUSTED_DIRECT,
        },
        {
            "name": "automation_actor_noop",
            "comment_user_type": "User",
            "comment_author": "alice",
            "comment_sender_type": "Organization",
            "installation_id": None,
            "performed_via_app": False,
            "comment_author_association": "MEMBER",
            "pr_head_full_name": "rustfoundation/safety-critical-rust-coding-guidelines",
            "pr_author": "carol",
            "route_outcome": comment_routing_policy.PrCommentRouterOutcome.TRUSTED_DIRECT,
        },
        {
            "name": "pull_request_read_failed",
            "comment_user_type": "User",
            "comment_author": "alice",
            "comment_sender_type": "User",
            "installation_id": None,
            "performed_via_app": False,
            "comment_author_association": "MEMBER",
            "pr_head_full_name": "",
            "pr_author": "",
            "pull_request_read_failed": True,
            "route_outcome": comment_routing_policy.PrCommentRouterOutcome.DEFERRED_RECONCILE,
        },
    ],
    ids=lambda scenario: scenario["name"],
)
def test_pr_comment_router_route_outcome_matches_core_policy(scenario):
    repo = "rustfoundation/safety-critical-rust-coding-guidelines"
    namespace = _load_pr_comment_router_inline_namespace()
    request = SimpleNamespace(
        is_pull_request=True,
        comment_user_type=scenario["comment_user_type"],
        comment_author=scenario["comment_author"],
        comment_sender_type=scenario["comment_sender_type"],
        comment_installation_id=scenario["installation_id"],
        comment_performed_via_github_app=scenario["performed_via_app"],
        comment_author_association=scenario["comment_author_association"],
    )
    pr_admission = PrCommentAdmission(
        route_outcome=scenario["route_outcome"],
        declared_trust_class="pr_trusted_direct",
        github_repository=repo,
        pr_head_full_name=scenario["pr_head_full_name"],
        pr_author=scenario["pr_author"],
        issue_state="open",
        issue_labels=(),
        comment_author_id=123,
        github_run_id=1,
        github_run_attempt=1,
    )
    actor_class = comment_routing_policy.classify_issue_comment_actor(request)
    processing_target = comment_routing_policy.classify_pr_comment_processing_target(
        request,
        pr_admission,
        actor_class=actor_class,
        is_self_comment=False,
    )
    expected = comment_routing_policy.route_issue_comment_trust(
        request,
        pr_admission,
        processing_target=processing_target,
    )
    workflow_actor_class = namespace["_classify_issue_comment_actor"](
        scenario["comment_user_type"],
        scenario["comment_author"],
        scenario["comment_sender_type"],
        scenario["installation_id"],
        scenario["performed_via_app"],
    )

    workflow_route = namespace["_route_pr_comment_outcome"](
        workflow_actor_class,
        repo,
        scenario["pr_head_full_name"],
        scenario["pr_author"],
        scenario["comment_author_association"],
        pull_request_read_failed=scenario.get("pull_request_read_failed", False),
    )

    assert workflow_actor_class == actor_class
    assert workflow_route == expected.value


def test_pr_comment_router_workflow_builds_payload_inline_without_bot_src_root():
    workflow = Path(".github/workflows/reviewer-bot-pr-comment-router.yml").read_text(encoding="utf-8")
    assert "build_pr_comment_observer_payload" not in workflow
    assert "Fetch trusted bot source tarball" in workflow

def test_pr_comment_router_workflow_contains_route_and_trusted_jobs_in_order():
    data = yaml.safe_load(Path(".github/workflows/reviewer-bot-pr-comment-router.yml").read_text(encoding="utf-8"))
    assert set(data["jobs"]) == {"route-pr-comment", "trusted-direct"}
    route_steps = data["jobs"]["route-pr-comment"]["steps"]
    trusted_steps = data["jobs"]["trusted-direct"]["steps"]
    assert route_steps[0]["name"] == "Route PR comment"
    assert route_steps[1]["name"] == "Upload deferred comment artifact"
    assert trusted_steps[0]["name"] == "Install uv"
    assert trusted_steps[1]["name"] == "Fetch trusted bot source tarball"
    assert trusted_steps[2]["name"] == "Run reviewer bot"

def test_pr_comment_router_upload_is_emitted_only_for_deferred_reconcile():
    data = yaml.safe_load(Path(".github/workflows/reviewer-bot-pr-comment-router.yml").read_text(encoding="utf-8"))
    upload_step = data["jobs"]["route-pr-comment"]["steps"][1]
    assert upload_step["if"] == "${{ steps.route.outputs.route_outcome == 'deferred_reconcile' }}"

def test_review_comment_observer_workflow_exists_and_is_read_only():
    data = yaml.safe_load(
        Path(".github/workflows/reviewer-bot-pr-review-comment-observer.yml").read_text(encoding="utf-8")
    )
    on_block = data.get("on", data.get(True))
    assert on_block["pull_request_review_comment"]["types"] == ["created"]
    job = data["jobs"]["observer"]
    assert job["permissions"]["contents"] == "read"
    steps = job["steps"]
    assert steps[0]["name"] == "Build deferred review comment artifact"
    assert steps[1]["name"] == "Upload deferred review comment artifact"
    workflow_text = Path(".github/workflows/reviewer-bot-pr-review-comment-observer.yml").read_text(
        encoding="utf-8"
    )
    assert "checkout" not in workflow_text
    assert "pull_request_review_comment" in workflow_text

def test_mutating_reviewer_bot_workflows_do_not_share_global_github_concurrency():
    workflow_paths = [
        ".github/workflows/reviewer-bot-issues.yml",
        ".github/workflows/reviewer-bot-issue-comment-direct.yml",
        ".github/workflows/reviewer-bot-sweeper-repair.yml",
        ".github/workflows/reviewer-bot-pr-metadata.yml",
        ".github/workflows/reviewer-bot-pr-comment-router.yml",
        ".github/workflows/reviewer-bot-reconcile.yml",
        ".github/workflows/reviewer-bot-privileged-commands.yml",
    ]
    for workflow_path in workflow_paths:
        data = yaml.safe_load(Path(workflow_path).read_text(encoding="utf-8"))
        for job in data.get("jobs", {}).values():
            assert "concurrency" not in job

def test_workflow_policy_split_and_lock_only_boundaries():
    workflows_dir = Path(".github/workflows")
    required = {
        "reviewer-bot-issues.yml",
        "reviewer-bot-issue-comment-direct.yml",
        "reviewer-bot-preview.yml",
        "reviewer-bot-sweeper-repair.yml",
        "reviewer-bot-pr-metadata.yml",
        "reviewer-bot-pr-comment-router.yml",
        "reviewer-bot-pr-review-submitted-observer.yml",
        "reviewer-bot-pr-review-dismissed-observer.yml",
        "reviewer-bot-pr-review-comment-observer.yml",
        "reviewer-bot-reconcile.yml",
        "reviewer-bot-privileged-commands.yml",
    }
    assert required.issubset({path.name for path in workflows_dir.glob("reviewer-bot-*.yml")})
    for path in required:
        data = yaml.safe_load((workflows_dir / path).read_text(encoding="utf-8"))
        jobs = data.get("jobs", {})
        for job in jobs.values():
            permissions = job.get("permissions", {})
            steps = job.get("steps", [])
            uses_values = [step.get("uses", "") for step in steps if isinstance(step, dict)]
            text = (workflows_dir / path).read_text(encoding="utf-8")
            if "observer" in path:
                assert permissions.get("contents") == "read"
                assert all("checkout" not in value for value in uses_values)
            if permissions.get("contents") == "write" and path not in {
                "reviewer-bot-privileged-commands.yml",
                "reviewer-bot-pr-comment-router.yml",
            }:
                assert all("checkout" not in value for value in uses_values)
                assert "Temporary lock debt" in text
            for value in uses_values:
                if value:
                    assert "@" in value and len(value.split("@", 1)[1]) == 40

def test_workflow_summaries_and_runbook_references_exist():
    runbook = Path("docs/reviewer-bot-review-freshness-operator-runbook.md")
    assert runbook.exists()
    reconcile = Path(".github/workflows/reviewer-bot-reconcile.yml").read_text(encoding="utf-8")
    assert "docs/reviewer-bot-review-freshness-operator-runbook.md" in reconcile


def test_reconcile_workflow_selects_at_most_one_recursive_json_payload():
    workflow_text = Path(".github/workflows/reviewer-bot-reconcile.yml").read_text(encoding="utf-8")

    assert "files = sorted(Path(os.environ['RUNNER_TEMP']).joinpath('observer-artifact').rglob('*.json'))" in workflow_text
    assert "if len(files) > 1:" in workflow_text
    assert "Expected at most one deferred payload" in workflow_text
    assert "if len(files) == 1:" in workflow_text
    assert "DEFERRED_CONTEXT_PATH=" in workflow_text


@pytest.mark.parametrize(
    ("fixture_path", "workflow_file", "payload_kind", "expected_event_name", "expected_event_action"),
    [
        (
            "tests/fixtures/observer_payloads/workflow_pr_comment_deferred.json",
            ".github/workflows/reviewer-bot-pr-comment-router.yml",
            "deferred_comment",
            "issue_comment",
            "created",
        ),
        (
            "tests/fixtures/observer_payloads/workflow_pr_review_submitted_deferred.json",
            ".github/workflows/reviewer-bot-pr-review-submitted-observer.yml",
            "deferred_review_submitted",
            "pull_request_review",
            "submitted",
        ),
        (
            "tests/fixtures/observer_payloads/workflow_pr_review_dismissed_deferred.json",
            ".github/workflows/reviewer-bot-pr-review-dismissed-observer.yml",
            "deferred_review_dismissed",
            "pull_request_review",
            "dismissed",
        ),
        (
            "tests/fixtures/observer_payloads/workflow_pr_review_comment_deferred.json",
            ".github/workflows/reviewer-bot-pr-review-comment-observer.yml",
            "deferred_review_comment",
            "pull_request_review_comment",
            "created",
        ),
    ],
)
def test_observer_workflow_fixtures_match_trigger_event_shape(
    fixture_path, workflow_file, payload_kind, expected_event_name, expected_event_action
):
    matrix = _load_observer_contract_matrix()
    fixture_entry = next(
        item for item in matrix["payload_contracts"] if item["payload_kind"] == payload_kind
    )
    payload = _load_fixture_payload(fixture_path)
    workflow_text = Path(workflow_file).read_text(encoding="utf-8")
    workflow_data = yaml.safe_load(workflow_text)
    on_block = workflow_data.get("on", workflow_data.get(True))

    assert fixture_entry["owner"] == workflow_file
    assert fixture_entry["payload_kind"] == payload_kind
    assert payload["source_event_name"] == expected_event_name
    assert payload["source_event_action"] == expected_event_action
    assert expected_event_name in on_block
