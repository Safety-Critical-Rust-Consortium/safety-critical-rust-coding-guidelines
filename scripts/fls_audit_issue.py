import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts.fls_audit_issue_lib.errors import AuditIssueError
from scripts.fls_audit_issue_lib.github import GitHubClient
from scripts.fls_audit_issue_lib.reconcile import reconcile

DEFAULT_LABEL = "fls-audit"
DEFAULT_TITLE_PREFIX = "FLS audit:"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise AuditIssueError(f"Missing required environment variable: {name}")
    return value


def run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repository and run_id:
        return f"{server}/{repository}/actions/runs/{run_id}"
    return ""


def load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditIssueError(f"Unable to load {description} at {path}: {error}") from error
    if not isinstance(value, dict):
        raise AuditIssueError(f"{description} at {path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update FLS audit issues.")
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--report-md", required=True)
    parser.add_argument("--spec-lock", required=True)
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--title-prefix", default=DEFAULT_TITLE_PREFIX)
    args = parser.parse_args()
    try:
        report = load_json(Path(args.report_json), "audit report")
        spec_lock = load_json(Path(args.spec_lock), "spec lock")
        report_md = Path(args.report_md).read_text(encoding="utf-8")
        client = GitHubClient(require_env("GITHUB_TOKEN"), require_env("REPO_OWNER"), require_env("REPO_NAME"))
        print(reconcile(client, report, report_md, spec_lock, args.label, args.title_prefix, run_url()))
    except (AuditIssueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
