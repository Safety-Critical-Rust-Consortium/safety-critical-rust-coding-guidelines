"""Repository-wide uv bootstrap contract."""

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contract

WORKFLOWS_DIR = Path(".github/workflows")
WORKFLOWS = sorted([*WORKFLOWS_DIR.glob("*.yml"), *WORKFLOWS_DIR.glob("*.yaml")])
UV_COMMAND = re.compile(
    r"(?:^|&&|\|\||[;|()])\s*"
    r"(?:(?:if|then|do|command|exec|env|sudo|!)\s+)*"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*uvx?\b"
)
FORBIDDEN_BOOTSTRAP = re.compile(
    r"\bpip(?:3|x)?\b[^\n]*\binstall\b[^\n]*\buv\b"
    r"|astral\.sh/uv"
    r"|\buv\s+self\s+update\b",
    re.IGNORECASE,
)


def jobs():
    for path in WORKFLOWS:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_name, job in (workflow.get("jobs") or {}).items():
            yield path.name, job_name, job


def run_invokes_uv(run: str) -> bool:
    for line in run.splitlines():
        command = line.lstrip()
        if command.startswith(("#", "echo ", "printf ")):
            continue
        if UV_COMMAND.search(line):
            return True
    return False


def test_every_setup_uv_step_follows_a_root_checkout_in_the_same_job():
    violations = []
    for file_name, job_name, job in jobs():
        steps = job.get("steps") or []
        root_checkout_indexes = [
            index
            for index, step in enumerate(steps)
            if str(step.get("uses", "")).startswith("actions/checkout@")
            and str((step.get("with") or {}).get("path", ".")).strip() in {"", "."}
        ]
        for setup_index, step in enumerate(steps):
            if not str(step.get("uses", "")).startswith("astral-sh/setup-uv@"):
                continue
            if not any(checkout_index < setup_index for checkout_index in root_checkout_indexes):
                violations.append(f"{file_name}:{job_name} step {setup_index}")
    assert not violations, f"setup-uv runs before a workspace-root checkout: {violations}"


def test_setup_uv_never_overrides_the_repository_pin():
    violations = []
    for file_name, job_name, job in jobs():
        for step in job.get("steps") or []:
            if not str(step.get("uses", "")).startswith("astral-sh/setup-uv@"):
                continue
            with_ = step.get("with") or {}
            if "version" in with_:
                violations.append(f"{file_name}:{job_name} version={with_['version']!r}")
            if with_.get("version-file", "pyproject.toml") != "pyproject.toml":
                violations.append(f"{file_name}:{job_name} version-file={with_['version-file']!r}")
    assert not violations, f"setup-uv must take the version from pyproject.toml only: {violations}"


def test_no_workflow_installs_uv_outside_setup_uv():
    violations = []
    for file_name, job_name, job in jobs():
        for index, step in enumerate(job.get("steps") or []):
            run = str(step.get("run", "")).replace("\\\n", " ")
            if FORBIDDEN_BOOTSTRAP.search(run):
                violations.append(f"{file_name}:{job_name} step {index}")
    assert not violations, f"uv must be installed only via astral-sh/setup-uv: {violations}"


def test_every_job_that_runs_uv_installs_it_via_setup_uv():
    violations = []
    for file_name, job_name, job in jobs():
        steps = job.get("steps") or []
        runs_uv = any(run_invokes_uv(str(step.get("run", ""))) for step in steps)
        has_setup = any(
            str(step.get("uses", "")).startswith("astral-sh/setup-uv@") for step in steps
        )
        if runs_uv and not has_setup:
            violations.append(f"{file_name}:{job_name}")
    assert not violations, f"jobs run uv without a setup-uv step: {violations}"
