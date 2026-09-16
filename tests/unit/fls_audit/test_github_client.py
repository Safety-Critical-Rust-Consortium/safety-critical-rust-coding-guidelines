import json
from typing import Any

import pytest
import requests

from scripts.fls_audit_issue_lib import github
from scripts.fls_audit_issue_lib.errors import AuditIssueError


def response(
    status: int,
    value: object,
    *,
    link: str | None = None,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(value).encode()
    if link:
        result.headers["Link"] = link
    if headers:
        result.headers.update(headers)
    return result


class FakeSession:
    def __init__(self, responses: list[requests.Response | requests.RequestException]):
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.requests.append((method, url, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, requests.RequestException):
            raise result
        return result


def client(session: FakeSession, sleeps: list[float] | None = None) -> github.GitHubClient:
    return github.GitHubClient(
        "token",
        "owner",
        "repo",
        session=session,
        sleep=(sleeps.append if sleeps is not None else lambda _delay: None),
    )


def test_paginate_follows_link_header() -> None:
    second_url = "https://api.github.com/repositories/1/issues?page=2"
    session = FakeSession(
        [
            response(200, [{"number": 1}], link=f'<{second_url}>; rel="next"'),
            response(200, [{"number": 2}]),
        ]
    )

    values = client(session).issues()

    assert [value["number"] for value in values] == [1, 2]
    assert session.requests[1][1] == second_url
    assert session.requests[1][2]["params"] is None


@pytest.mark.parametrize(
    "next_url",
    [
        "http://api.github.com/repositories/1/issues?page=2",
        "https://example.test/repositories/1/issues?page=2",
        "https://api.github.com.example.test/repositories/1/issues?page=2",
        "https://api.github.com@example.test/repositories/1/issues?page=2",
        "https://example.test@api.github.com/repositories/1/issues?page=2",
        "https://api.github.com:444/repositories/1/issues?page=2",
    ],
)
def test_paginate_rejects_unsafe_next_link_before_second_request(next_url: str) -> None:
    session = FakeSession([response(200, [{"number": 1}], link=f'<{next_url}>; rel="next"')])

    with pytest.raises(AuditIssueError, match="outside https://api.github.com"):
        client(session).issues()

    assert len(session.requests) == 1


def test_ensure_label_url_encodes_name_and_creates_missing_label() -> None:
    session = FakeSession([response(404, {}), response(201, {"name": "FLS audit"})])

    client(session).ensure_label("FLS audit")

    assert session.requests[0][1].endswith("/labels/FLS%20audit")
    assert session.requests[1][0] == "POST"
    assert session.requests[1][2]["json"]["name"] == "FLS audit"


def test_api_error_includes_response_context() -> None:
    session = FakeSession([response(422, {"message": "invalid"})])

    with pytest.raises(github.GitHubAPIError, match="422") as raised:
        client(session).issue(42)

    assert raised.value.status == 422
    assert '"message": "invalid"' in raised.value.response_body


def test_safe_read_retries_network_failure() -> None:
    session = FakeSession([requests.ConnectionError("temporary"), response(200, {"number": 42})])
    sleeps: list[float] = []

    value = client(session, sleeps).issue(42)

    assert value["number"] == 42
    assert sleeps == [1]
    assert len(session.requests) == 2


def test_safe_read_honors_retry_after() -> None:
    session = FakeSession(
        [
            response(429, {"message": "slow down"}, headers={"Retry-After": "3"}),
            response(200, {"number": 42}),
        ]
    )
    sleeps: list[float] = []

    assert client(session, sleeps).issue(42)["number"] == 42
    assert sleeps == [3]


@pytest.mark.parametrize(
    ("status", "headers"),
    [
        (500, {}),
        (403, {"X-RateLimit-Remaining": "0"}),
    ],
)
def test_safe_read_retries_transient_http_status(status: int, headers: dict[str, str]) -> None:
    session = FakeSession([response(status, {"message": "temporary"}, headers=headers), response(200, {"number": 42})])
    sleeps: list[float] = []

    assert client(session, sleeps).issue(42)["number"] == 42
    assert sleeps == [1]


def test_authorization_error_is_not_retried() -> None:
    session = FakeSession([response(403, {"message": "forbidden"}), response(200, {"number": 42})])

    with pytest.raises(github.GitHubAPIError, match="403"):
        client(session).issue(42)

    assert len(session.requests) == 1


def test_retry_after_cannot_exceed_budget() -> None:
    session = FakeSession(
        [
            response(
                429,
                {"message": "slow down"},
                headers={"Retry-After": "16", "X-RateLimit-Reset": "12345"},
            )
        ]
    )

    with pytest.raises(AuditIssueError, match="rate-limit reset=12345"):
        client(session).issue(42)

    assert len(session.requests) == 1


def test_write_is_not_retried_after_transport_failure() -> None:
    session = FakeSession([requests.ConnectionError("ambiguous"), response(200, {"number": 42})])

    with pytest.raises(github.GitHubAPIError, match="ambiguous"):
        client(session).patch_issue(42, {"state": "closed"})

    assert len(session.requests) == 1
