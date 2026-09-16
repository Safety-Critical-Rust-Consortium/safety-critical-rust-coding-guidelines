import copy
from collections.abc import Callable
from typing import Any

from scripts.fls_audit_issue_lib.errors import AuditIssueError
from scripts.fls_audit_issue_lib.state import parse_state

BOT_USER = {"login": "github-actions[bot]", "id": 41898282, "type": "Bot"}


class FakeGitHubClient:
    def __init__(self) -> None:
        self.issue_values: dict[int, dict[str, Any]] = {}
        self.comment_values: dict[int, list[dict[str, Any]]] = {}
        self.next_issue = 2000
        self.next_comment = 1
        self.label_exists = True
        self.mutations: list[tuple[str, int | None]] = []
        self.failures: dict[str, str] = {}
        self.stale_after_write: dict[str, int] = {}
        self.stale_issue_values: dict[int, list[dict[str, Any]]] = {}
        self.hidden_issue_reads: dict[int, int] = {}
        self.hidden_comment_reads = 0
        self.read_failures: dict[str, int] = {}
        self.read_failures_after_write: dict[str, int] = {}
        self.issue_read_hook: Callable[[dict[str, Any]], None] | None = None
        self.sleep_delays: list[float] = []
        self.sleep = self.sleep_delays.append

    def fail(self, operation: str, timing: str) -> None:
        self.failures[operation] = timing

    def maybe_fail(self, operation: str, timing: str) -> None:
        if self.failures.get(operation) == timing:
            del self.failures[operation]
            raise AuditIssueError(f"{operation} failed {timing} write")

    def ensure_label(self, _label: str) -> None:
        if self.label_exists:
            return
        self.mutations.append(("label", None))
        self.maybe_fail("label", "before")
        self.label_exists = True
        self.maybe_fail("label", "after")

    def issues(self) -> list[dict[str, Any]]:
        if self.read_failures.get("issues", 0):
            self.read_failures["issues"] -= 1
            raise AuditIssueError("issues read failed")
        values = []
        for number, value in self.issue_values.items():
            if self.hidden_issue_reads.get(number, 0):
                self.hidden_issue_reads[number] -= 1
                continue
            stale = self.stale_issue_values.get(number, [])
            values.append(copy.deepcopy(stale.pop(0) if stale else value))
        return values

    def issue(self, number: int) -> dict[str, Any]:
        stale = self.stale_issue_values.get(number, [])
        if stale:
            return copy.deepcopy(stale.pop(0))
        if self.issue_read_hook is not None:
            hook = self.issue_read_hook
            self.issue_read_hook = None
            hook(self.issue_values[number])
        return copy.deepcopy(self.issue_values[number])

    def comments(self, number: int) -> list[dict[str, Any]]:
        if self.read_failures.get("comments", 0):
            self.read_failures["comments"] -= 1
            raise AuditIssueError("comments read failed")
        values = self.comment_values.get(number, [])
        if self.hidden_comment_reads and values:
            self.hidden_comment_reads -= 1
            values = values[:-1]
        return copy.deepcopy(values)

    def patch_issue(self, number: int, data: dict[str, Any]) -> dict[str, Any]:
        self.mutations.append(("patch", number))
        operation = "body_patch" if "body" in data else "state_patch" if "state" in data else "identity_patch"
        self.maybe_fail(operation, "before")
        value = self.issue_values[number]
        previous = copy.deepcopy(value)
        patch = copy.deepcopy(data)
        if "labels" in patch:
            patch["labels"] = [{"name": label} for label in patch["labels"]]
        value.update(patch)
        if data.get("state") == "open":
            value["state_reason"] = "reopened"
        stale_reads = self.stale_after_write.pop(operation, 0)
        self.stale_issue_values.setdefault(number, []).extend(copy.deepcopy(previous) for _ in range(stale_reads))
        self.maybe_fail(operation, "after")
        return copy.deepcopy(value)

    def create_issue(self, title: str, body: str, label: str) -> dict[str, Any]:
        number = self.next_issue
        self.mutations.append(("create", number))
        self.maybe_fail("create", "before")
        value = {
            "number": number,
            "title": title,
            "body": body,
            "labels": [{"name": label}],
            "state": "open",
            "user": copy.deepcopy(BOT_USER),
        }
        self.next_issue += 1
        self.issue_values[number] = value
        self.hidden_issue_reads[number] = self.stale_after_write.pop("create", 0)
        self.read_failures["issues"] = self.read_failures_after_write.pop("create", 0)
        self.maybe_fail("create", "after")
        return copy.deepcopy(value)

    def post_comment(self, number: int, body: str) -> dict[str, Any]:
        self.mutations.append(("comment", number))
        self.maybe_fail("comment", "before")
        value = {"id": self.next_comment, "body": body, "user": copy.deepcopy(BOT_USER)}
        self.next_comment += 1
        self.comment_values.setdefault(number, []).append(value)
        self.hidden_comment_reads = self.stale_after_write.pop("comment", 0)
        self.read_failures["comments"] = self.read_failures_after_write.pop("comment", 0)
        self.maybe_fail("comment", "after")
        return copy.deepcopy(value)


def current_issue(client: FakeGitHubClient) -> tuple[int, dict[str, Any], dict[str, Any]]:
    number = max(client.issue_values)
    issue = client.issue_values[number]
    issue_state = parse_state(issue["body"])
    assert issue_state is not None
    return number, issue, issue_state
