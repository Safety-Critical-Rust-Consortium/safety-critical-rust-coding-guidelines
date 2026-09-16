import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlsplit

import requests

from .errors import AuditIssueError

DEFAULT_LABEL_COLOR = "0e8a16"
READ_RETRY_DELAYS = (1, 2, 4, 8)
READ_RETRY_BUDGET_SECONDS = 15


class GitHubAPIError(AuditIssueError):
    def __init__(
        self,
        method: str,
        endpoint: str,
        message: str,
        *,
        status: int | None = None,
        response_body: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.method = method
        self.endpoint = endpoint
        self.status = status
        self.response_body = response_body
        self.headers = headers or {}
        context = f"{status} {response_body}" if status is not None else message
        super().__init__(f"GitHub {method} {endpoint} failed: {context}")

    @property
    def retry_after(self) -> int | None:
        value = self.headers.get("Retry-After")
        if value is None:
            return None
        try:
            delay = int(value)
        except ValueError:
            return None
        return delay if delay >= 0 else None

    @property
    def retryable_read(self) -> bool:
        if self.status is None:
            return True
        if self.status == 429 or self.status >= 500:
            return True
        return self.status == 403 and (
            "Retry-After" in self.headers or self.headers.get("X-RateLimit-Remaining") == "0"
        )

    def retry_budget_message(self, delay: int, remaining: int) -> str:
        reset = self.headers.get("X-RateLimit-Reset", "unknown")
        return (
            f"{self}; requested retry delay {delay}s exceeds remaining {remaining}s budget; "
            f"rate-limit reset={reset}"
        )


class GitHubClient:
    def __init__(
        self,
        token: str,
        owner: str,
        repo: str,
        session: requests.Session | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.session = session or requests.Session()
        self.sleep = sleep
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def url(self, endpoint: str) -> str:
        parsed = urlsplit(endpoint)
        if not parsed.scheme and not parsed.netloc:
            return f"https://api.github.com/repos/{self.owner}/{self.repo}/{endpoint}"
        try:
            port = parsed.port
        except ValueError as error:
            raise AuditIssueError(f"GitHub API URL has an invalid port: {endpoint}") from error
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.github.com"
            or port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise AuditIssueError(f"Refusing GitHub API URL outside https://api.github.com: {endpoint}")
        return endpoint

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> requests.Response:
        if method == "GET":
            return self.retry_read(endpoint, params=params, allowed_statuses=allowed_statuses)
        return self.request_once(method, endpoint, data=data, params=params, allowed_statuses=allowed_statuses)

    def request_once(
        self,
        method: str,
        endpoint: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> requests.Response:
        try:
            response = self.session.request(method, self.url(endpoint), json=data, params=params, timeout=30)
        except requests.RequestException as error:
            raise GitHubAPIError(method, endpoint, str(error)) from error
        if response.status_code >= 400 and response.status_code not in (allowed_statuses or set()):
            raise GitHubAPIError(
                method,
                endpoint,
                response.text,
                status=response.status_code,
                response_body=response.text,
                headers=dict(response.headers),
            )
        return response

    def retry_read(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> requests.Response:
        spent = 0
        for attempt in range(len(READ_RETRY_DELAYS) + 1):
            try:
                return self.request_once("GET", endpoint, params=params, allowed_statuses=allowed_statuses)
            except GitHubAPIError as error:
                if not error.retryable_read or attempt == len(READ_RETRY_DELAYS):
                    raise
                delay = error.retry_after
                if delay is None:
                    delay = READ_RETRY_DELAYS[attempt]
                remaining = READ_RETRY_BUDGET_SECONDS - spent
                if delay > remaining:
                    raise AuditIssueError(error.retry_budget_message(delay, remaining)) from error
                self.sleep(delay)
                spent += delay
        raise AssertionError("unreachable")

    def json(self, response: requests.Response) -> object:
        if not response.content:
            return {}
        try:
            return response.json()
        except requests.JSONDecodeError as error:
            raise AuditIssueError("GitHub response was not valid JSON") from error

    def paginate(self, endpoint: str, params: dict[str, str]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        next_endpoint: str | None = endpoint
        next_params: dict[str, str] | None = params
        while next_endpoint:
            response = self.request("GET", next_endpoint, params=next_params)
            data = self.json(response)
            if not isinstance(data, list):
                raise AuditIssueError(f"GitHub pagination response for {endpoint} was not a list")
            values.extend(value for value in data if isinstance(value, dict))
            next_endpoint = response.links.get("next", {}).get("url")
            next_params = None
        return values

    def ensure_label(self, label: str) -> None:
        endpoint = f"labels/{quote(label, safe='')}"
        response = self.request("GET", endpoint, allowed_statuses={404})
        if response.status_code == 200:
            return
        self.request(
            "POST",
            "labels",
            data={"name": label, "color": DEFAULT_LABEL_COLOR, "description": "FLS audit results"},
        )

    def issues(self) -> list[dict[str, Any]]:
        return self.paginate("issues", {"state": "all", "per_page": "100"})

    def issue(self, number: int) -> dict[str, Any]:
        value = self.json(self.request("GET", f"issues/{number}"))
        if not isinstance(value, dict):
            raise AuditIssueError(f"GitHub issue #{number} response was malformed")
        return value

    def comments(self, number: int) -> list[dict[str, Any]]:
        return self.paginate(f"issues/{number}/comments", {"per_page": "100"})

    def patch_issue(self, number: int, data: dict[str, Any]) -> dict[str, Any]:
        value = self.json(self.request("PATCH", f"issues/{number}", data=data))
        if not isinstance(value, dict):
            raise AuditIssueError(f"GitHub issue #{number} update response was malformed")
        return value

    def create_issue(self, title: str, body: str, label: str) -> dict[str, Any]:
        value = self.json(self.request("POST", "issues", data={"title": title, "body": body, "labels": [label]}))
        if not isinstance(value, dict) or not value.get("number"):
            raise AuditIssueError("GitHub create issue response was malformed")
        return value

    def post_comment(self, number: int, body: str) -> None:
        self.request("POST", f"issues/{number}/comments", data={"body": body})
