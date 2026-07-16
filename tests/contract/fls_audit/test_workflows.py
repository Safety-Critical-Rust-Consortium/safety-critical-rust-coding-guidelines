import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def load_workflow(name: str) -> dict:
    return yaml.load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def assert_checkout_precedes_script(job: dict, command: str) -> None:
    steps = job["steps"]
    checkout_index = next(index for index, step in enumerate(steps) if step.get("uses") == "actions/checkout@v4")
    script_index = next(index for index, step in enumerate(steps) if step.get("run") == command)
    assert checkout_index < script_index


@pytest.mark.contract
def test_netlify_uses_required_uv_version() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    netlify = tomllib.loads((ROOT / "netlify.toml").read_text(encoding="utf-8"))

    required_version = project["tool"]["uv"]["required-version"]
    assert required_version.startswith("==")
    assert netlify["build"]["environment"]["UV_VERSION"] == required_version.removeprefix("==")
    assert netlify["build"]["command"] == (
        "curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh "
        "&& uv run --frozen make.py"
    )
    assert netlify["build"]["publish"] == "build/html"


@pytest.mark.contract
def test_build_freshness_policy_and_required_context() -> None:
    workflow = load_workflow("build-guidelines.yml")

    assert "build" in workflow["jobs"]
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert "pull_request" in workflow["on"]
    assert "merge_group" in workflow["on"]
    assert "tags" not in workflow["on"]["push"]
    enforce = workflow["on"]["workflow_call"]["inputs"]["enforce_spec_lock"]
    assert enforce["type"] == "boolean"
    assert enforce["default"] == "false"
    offline = workflow["on"]["workflow_call"]["inputs"]["offline"]
    assert offline["type"] == "boolean"
    assert offline["default"] == "false"
    test_job = workflow["jobs"]["fls_audit_tests"]
    test_step = next(step for step in test_job["steps"] if step.get("name") == "Run FLS audit tests")
    assert "uv run --frozen pytest" in test_step["run"]
    assert "tests/unit/fls_audit" in test_step["run"]
    assert "tests/integration/fls_audit" in test_step["run"]
    assert "tests/contract/fls_audit" in test_step["run"]
    build = workflow["jobs"]["build"]
    assert set(build["needs"]) == {"gatekeeper", "check_rust_examples", "fls_audit_tests"}
    assert "always()" in build["if"]
    assert "needs.gatekeeper.outputs.run_all == 'true'" in build["if"]
    prerequisite = next(step for step in build["steps"] if step.get("name") == "Fail if prerequisite checks failed")
    assert "needs.check_rust_examples.result" in prerequisite["if"]
    assert "needs.fls_audit_tests.result" in prerequisite["if"]
    assert "exit 1" in prerequisite["run"]
    assert all(step.get("name") != "Run FLS audit tests" for step in build["steps"])
    build_step = next(step for step in build["steps"] if step.get("name") == "Build documentation")
    assert "inputs.enforce_spec_lock" in build_step["env"]["ENFORCE_SPEC_LOCK"]
    assert "inputs.offline" in build_step["env"]["OFFLINE_BUILD"]
    assert build_step["shell"] == "bash"
    assert "--offline" in build_step["run"]
    assert "--enforce-spec-lock-diff" in build_step["run"]
    assert "--ignore-spec-lock-diff" not in build_step["run"]
    assert "PIPESTATUS[0]" in build_step["run"]
    assert "::warning title=FLS validation::" in build_step["run"]


@pytest.mark.contract
def test_nightly_preflight_and_deploy_freshness_policy() -> None:
    nightly = load_workflow("nightly.yml")
    preflight = load_workflow("release-preflight.yml")
    deploy = load_workflow("deploy.yml")

    assert nightly["jobs"]["run-build"]["with"]["enforce_spec_lock"] == "true"
    assert set(preflight["on"]) == {"workflow_dispatch"}
    release_sha = preflight["on"]["workflow_dispatch"]["inputs"]["release_sha"]
    assert release_sha["required"] == "true"
    assert release_sha["type"] == "string"
    assert preflight["permissions"] == {}
    validate = preflight["jobs"]["validate"]
    assert validate["permissions"] == {"contents": "read", "statuses": "write"}
    ancestry = next(step for step in validate["steps"] if step.get("name") == "Require commit from default branch")
    assert "inputs.release_sha" in ancestry["env"]["RELEASE_SHA"]
    assert '"$RELEASE_SHA" != "$GITHUB_SHA"' in ancestry["run"]
    assert "git merge-base --is-ancestor" in ancestry["run"]
    pending = next(step for step in validate["steps"] if step.get("name") == "Mark preflight pending")
    assert pending["run"] == "bash scripts/fls_release_status.sh pending"
    assert_checkout_precedes_script(validate, pending["run"])
    assert preflight["jobs"]["build"]["with"]["enforce_spec_lock"] == "true"
    assert preflight["jobs"]["build"]["needs"] == "validate"
    record = preflight["jobs"]["record"]
    assert record["if"] == "always()"
    assert set(record["needs"]) == {"validate", "build"}
    assert record["permissions"] == {"contents": "read", "statuses": "write"}
    record_step = next(step for step in record["steps"] if step.get("name") == "Record preflight result")
    assert record_step["run"] == "bash scripts/fls_release_status.sh preflight-result"
    assert_checkout_precedes_script(record, record_step["run"])

    assert deploy["permissions"] == {}
    authorization = deploy["jobs"]["authorize-release"]
    assert authorization["permissions"] == {"contents": "read", "statuses": "read"}
    authorize_step = next(step for step in authorization["steps"] if step.get("name") == "Authorize release")
    assert authorize_step["run"] == "bash scripts/fls_release_status.sh authorize"
    assert_checkout_precedes_script(authorization, authorize_step["run"])
    assert authorize_step["env"]["PREFLIGHT_MAX_AGE_SECONDS"] == "86400"
    assert authorize_step["env"]["PREFLIGHT_FUTURE_TOLERANCE_SECONDS"] == "300"
    assert deploy["jobs"]["build"]["needs"] == "authorize-release"
    assert deploy["jobs"]["build"]["with"]["offline"] == "true"
    assert deploy["jobs"]["deploy"]["needs"] == "build"
    assert deploy["jobs"]["deploy"]["permissions"] == {
        "actions": "read",
        "contents": "write",
        "statuses": "write",
    }
    deploy_steps = deploy["jobs"]["deploy"]["steps"]
    pages_index = next(index for index, step in enumerate(deploy_steps) if step.get("name") == "Deploy to GitHub Pages")
    status_index = next(
        index for index, step in enumerate(deploy_steps) if step.get("name") == "Record successful deployment"
    )
    assert status_index > pages_index
    assert deploy_steps[status_index]["run"] == "bash scripts/fls_release_status.sh deployed"
    assert_checkout_precedes_script(deploy["jobs"]["deploy"], deploy_steps[status_index]["run"])

    release_script = (ROOT / "scripts" / "fls_release_status.sh").read_text(encoding="utf-8")
    assert 'commits/$GITHUB_SHA/status"' in release_script
    assert "--paginate" in release_script
    assert "--jq '.statuses[] | [.context, .state, .created_at] | @tsv'" in release_script
    assert "statuses?per_page" not in release_script
    assert all(not line.lstrip().startswith("jq ") for line in release_script.splitlines())


@pytest.mark.contract
def test_audit_schedule_manual_guard_permissions_and_artifact() -> None:
    workflow = load_workflow("fls-audit.yml")

    assert workflow["on"]["schedule"][0]["cron"] == "23 4 * * *"
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"] == {"contents": "read", "issues": "write"}
    assert workflow["concurrency"] == {"group": "fls-audit", "cancel-in-progress": "false"}
    steps = workflow["jobs"]["fls-audit"]["steps"]
    guard = next(step for step in steps if step.get("name") == "Require default branch for manual runs")
    assert 'GITHUB_REF" != "refs/heads/$DEFAULT_BRANCH' in guard["run"]
    update = next(step for step in steps if step.get("name") == "Update audit issue")
    assert "--spec-lock src/spec.lock" in update["run"]
    artifact = next(step for step in steps if step.get("name") == "Upload audit reports")
    assert artifact["if"] == "always()"
    assert artifact["with"]["retention-days"] == "90"
