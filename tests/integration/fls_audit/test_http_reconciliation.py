import copy
import json
import re
from typing import Any
from urllib.parse import unquote, urlparse

import pytest
import requests
from requests.adapters import BaseAdapter

from scripts.fls_audit_issue_lib import reconcile as reconciliation
from scripts.fls_audit_issue_lib.github import GitHubClient
from scripts.fls_audit_issue_lib.state import parse_state
from tests.fls_audit_fixtures import report_with_changes, spec_lock
from tests.integration.fls_audit.fake_github import FakeGitHubClient

BOT_USER = {
    "login": reconciliation.ACTIONS_BOT_LOGIN,
    "id": reconciliation.ACTIONS_BOT_ID,
    "type": "Bot",
}


class GitHubAdapter(BaseAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.labels: set[str] = set()
        self.issues: dict[int, dict[str, Any]] = {}
        self.comments: dict[int, list[dict[str, Any]]] = {}
        self.requests: list[requests.PreparedRequest] = []
        self.next_issue = 2000
        self.next_comment = 1

    def close(self) -> None:
        return

    def response(
        self, request: requests.PreparedRequest, status: int, value: object
    ) -> requests.Response:
        result = requests.Response()
        result.status_code = status
        result._content = json.dumps(value).encode()
        result.headers["Content-Type"] = "application/json"
        result.request = request
        result.url = request.url
        return result

    def body(self, request: requests.PreparedRequest) -> dict[str, Any]:
        value = json.loads(request.body or b"{}")
        assert isinstance(value, dict)
        return value

    def send(self, request: requests.PreparedRequest, **_kwargs: Any) -> requests.Response:
        self.requests.append(request)
        prefix = "/repos/owner/repo/"
        path = urlparse(request.url).path
        assert path.startswith(prefix)
        endpoint = path.removeprefix(prefix)
        method = request.method

        if endpoint.startswith("labels/") and method == "GET":
            label = unquote(endpoint.removeprefix("labels/"))
            return self.response(request, 200, {"name": label}) if label in self.labels else self.response(request, 404, {})
        if endpoint == "labels" and method == "POST":
            value = self.body(request)
            self.labels.add(str(value["name"]))
            return self.response(request, 201, value)
        if endpoint == "issues" and method == "GET":
            return self.response(request, 200, list(self.issues.values()))
        if endpoint == "issues" and method == "POST":
            value = self.body(request)
            number = self.next_issue
            self.next_issue += 1
            issue = {
                "number": number,
                "title": value["title"],
                "body": value["body"],
                "labels": [{"name": label} for label in value["labels"]],
                "state": "open",
                "user": copy.deepcopy(BOT_USER),
            }
            self.issues[number] = issue
            return self.response(request, 201, issue)

        match = re.fullmatch(r"issues/(\d+)(/comments)?", endpoint)
        assert match is not None, endpoint
        number = int(match.group(1))
        if match.group(2) == "/comments":
            if method == "GET":
                return self.response(request, 200, self.comments.get(number, []))
            assert method == "POST"
            comment = {
                "id": self.next_comment,
                "body": self.body(request)["body"],
                "user": copy.deepcopy(BOT_USER),
            }
            self.next_comment += 1
            self.comments.setdefault(number, []).append(comment)
            return self.response(request, 201, comment)
        if method == "GET":
            return self.response(request, 200, self.issues[number])
        assert method == "PATCH"
        patch = self.body(request)
        if "labels" in patch:
            patch["labels"] = [{"name": label} for label in patch["labels"]]
        self.issues[number].update(patch)
        return self.response(request, 200, self.issues[number])


@pytest.mark.integration
def test_production_and_fake_clients_satisfy_issue_client_protocol() -> None:
    assert isinstance(GitHubClient("secret", "owner", "repo"), reconciliation.IssueClient)
    assert isinstance(FakeGitHubClient(), reconciliation.IssueClient)


@pytest.mark.integration
def test_real_github_client_reconciles_over_fake_http_transport() -> None:
    session = requests.Session()
    adapter = GitHubAdapter()
    session.mount("https://api.github.com/", adapter)
    client = GitHubClient("secret", "owner", "repo", session=session)

    reconciliation.reconcile(client, report_with_changes(), "# Report\n", spec_lock(), "fls-audit", "FLS audit:")
    changed = report_with_changes(live_checksum="live-b")
    reconciliation.reconcile(client, changed, "# Report\n", spec_lock(), "fls-audit", "FLS audit:")
    writes = len([request for request in adapter.requests if request.method in {"POST", "PATCH"}])
    reconciliation.reconcile(client, changed, "# Report\n", spec_lock(), "fls-audit", "FLS audit:")

    assert len(adapter.issues) == 1
    number, issue = next(iter(adapter.issues.items()))
    state = parse_state(issue["body"])
    assert state is not None and state["sequence"] == 1
    assert len(adapter.comments[number]) == 1
    assert len([request for request in adapter.requests if request.method in {"POST", "PATCH"}]) == writes
    assert all(request.headers["Authorization"] == "Bearer secret" for request in adapter.requests)
