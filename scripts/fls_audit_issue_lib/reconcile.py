from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from .errors import AuditIssueError
from .render import (
    comparable_managed_body,
    event_comment,
    managed_body,
    transition_comment,
)
from .state import (
    DEFAULT_BODY_LIMITS,
    MANAGED_END,
    MANAGED_START,
    BodyLimits,
    batch_id,
    campaign_id,
    canonical_items,
    compact_json,
    make_applied,
    make_state,
    parse_batch_marker,
    parse_state,
    sha256_json,
)

ACTIONS_BOT_LOGIN = "github-actions[bot]"
ACTIONS_BOT_ID = 41898282
CONFIRMATION_DELAYS = (0, 1, 2, 4, 8)
VERIFICATION_DELAYS = (0, 1, 2)


@runtime_checkable
class IssueClient(Protocol):
    sleep: Callable[[float], None]

    def ensure_label(self, label: str) -> None: ...

    def issues(self) -> list[dict[str, Any]]: ...

    def issue(self, number: int) -> dict[str, Any]: ...

    def comments(self, number: int) -> list[dict[str, Any]]: ...

    def patch_issue(self, number: int, data: dict[str, Any]) -> dict[str, Any]: ...

    def create_issue(self, title: str, body: str, label: str) -> dict[str, Any]: ...

    def post_comment(self, number: int, body: str) -> object: ...


def issue_labels(issue: dict[str, Any]) -> list[str]:
    labels = issue.get("labels", [])
    if not isinstance(labels, list):
        return []
    return sorted(str(label["name"]) for label in labels if isinstance(label, dict) and label.get("name"))


def is_actions_bot_record(value: dict[str, Any]) -> bool:
    user = value.get("user")
    return (
        isinstance(user, dict)
        and user.get("login") == ACTIONS_BOT_LOGIN
        and user.get("id") == ACTIONS_BOT_ID
        and user.get("type") == "Bot"
    )


def audit_issues(
    issues: list[dict[str, Any]],
    title_prefix: str,
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    result = []
    for issue in issues:
        if "pull_request" in issue or not is_actions_bot_record(issue):
            continue
        body = str(issue.get("body") or "")
        closed_markerless = issue.get("state") == "closed" and not any(
            marker in body for marker in ("fls-audit:state:", MANAGED_START, MANAGED_END)
        )
        state = None if closed_markerless else parse_state(body, limits)
        if state is not None or str(issue.get("title") or "").startswith(title_prefix):
            result.append((issue, state))
    return result


def find_campaign(
    issues: list[tuple[dict[str, Any], dict[str, Any] | None]],
    campaign: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    matches = [(issue, state) for issue, state in issues if state and state.get("campaign") == campaign]
    if len(matches) > 1:
        numbers = ", ".join(f"#{issue.get('number')}" for issue, _ in matches)
        raise AuditIssueError(f"Multiple FLS audit issues claim campaign {campaign}: {numbers}")
    return matches[0] if matches else None


def expected_title(title_prefix: str, campaign: str) -> str:
    return f"{title_prefix} spec.lock drift ({campaign.removeprefix('sha256:')[:12]})"


def refresh_issue_identity(
    client: IssueClient,
    issue: dict[str, Any],
    title: str,
    label: str,
) -> tuple[dict[str, Any], bool]:
    patch: dict[str, Any] = {}
    if issue.get("title") != title:
        patch["title"] = title
    labels = issue_labels(issue)
    if label not in labels:
        patch["labels"] = sorted([*labels, label])
    return (client.patch_issue(int(issue["number"]), patch), True) if patch else (issue, False)


def comment_markers(
    comments: list[dict[str, Any]],
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> list[dict[str, Any]]:
    markers = [
        marker
        for comment in comments
        if is_actions_bot_record(comment)
        and (marker := parse_batch_marker(str(comment.get("body") or ""), limits)) is not None
    ]
    seen: set[str] = set()
    duplicates: set[str] = set()
    for marker in markers:
        value = marker["batch_id"]
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        values = ", ".join(sorted(duplicates))
        raise AuditIssueError(f"FLS audit issue contains duplicate bot batch markers: {values}")
    return markers


def verify_comment_history(
    state: dict[str, Any],
    comments: list[dict[str, Any]],
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> None:
    transitions = [
        marker
        for marker in comment_markers(comments, limits)
        if marker.get("campaign") == state["campaign"] and marker.get("applied") is not None
    ]
    by_sequence: dict[int, dict[str, Any]] = {}
    for marker in transitions:
        sequence = int(marker["sequence"])
        if sequence in by_sequence:
            raise AuditIssueError(f"FLS audit issue contains multiple bot transitions at sequence {sequence}")
        by_sequence[sequence] = marker

    expected_sequences = set(range(1, int(state["sequence"]) + 1))
    actual_sequences = set(by_sequence)
    if actual_sequences != expected_sequences:
        raise AuditIssueError(
            "FLS audit comment history does not match issue sequence "
            f"{state['sequence']}: found {sorted(actual_sequences)}"
        )
    if not by_sequence:
        return

    latest = by_sequence[int(state["sequence"])]["applied"]
    if latest["semantic_digest"] != state["applied"]["semantic_digest"]:
        raise AuditIssueError("Latest FLS audit comment does not match the issue semantic state")
    for sequence in range(1, int(state["sequence"]) + 1):
        previous_digest = (
            state["origin_semantic_digest"]
            if sequence == 1
            else by_sequence[sequence - 1]["applied"]["semantic_digest"]
        )
        current = by_sequence[sequence]["applied"]
        expected = batch_id(state["campaign"], sequence, previous_digest, current["semantic_digest"])
        if (
            by_sequence[sequence]["previous_semantic_digest"] != previous_digest
            or by_sequence[sequence]["batch_id"] != expected
        ):
            raise AuditIssueError(f"FLS audit comment at sequence {sequence} has an invalid historical batch chain")


def recover_from_comments(
    state: dict[str, Any],
    comments: list[dict[str, Any]],
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> tuple[dict[str, Any], bool]:
    candidates = [
        marker
        for marker in comment_markers(comments, limits)
        if marker.get("campaign") == state["campaign"]
        and isinstance(marker.get("sequence"), int)
        and marker.get("applied") is not None
    ]
    if not candidates:
        return state, False
    by_sequence: dict[int, dict[str, Any]] = {}
    for marker in candidates:
        sequence = int(marker["sequence"])
        existing = by_sequence.get(sequence)
        if existing is not None and compact_json(existing) != compact_json(marker):
            raise AuditIssueError(f"Audit comments conflict at sequence {sequence}")
        by_sequence[sequence] = marker

    same = by_sequence.get(int(state["sequence"]))
    if same and same["applied"]["semantic_digest"] != state["applied"]["semantic_digest"]:
        raise AuditIssueError("Issue state conflicts with an audit comment at the same sequence")

    previous = state["applied"]
    expected_sequence = int(state["sequence"]) + 1
    recovered = False
    for sequence, marker in sorted(by_sequence.items()):
        if sequence < expected_sequence:
            continue
        if sequence != expected_sequence:
            raise AuditIssueError(f"Audit comment sequence jumps from {expected_sequence - 1} to {sequence}")
        applied = marker["applied"]
        expected_batch = batch_id(
            state["campaign"], sequence, previous["semantic_digest"], applied["semantic_digest"]
        )
        if (
            marker["previous_semantic_digest"] != previous["semantic_digest"]
            or marker["batch_id"] != expected_batch
        ):
            raise AuditIssueError(f"Audit comment at sequence {sequence} has an invalid batch chain")
        previous = applied
        expected_sequence += 1
        recovered = True
    return (
        make_state(state["campaign"], expected_sequence - 1, previous, state["origin_semantic_digest"])
        if recovered
        else state,
        recovered,
    )


def post_comment_once(
    client: IssueClient,
    issue_number: int,
    body: str,
    value: str,
    comments: list[dict[str, Any]],
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> None:
    if any(marker.get("batch_id") == value for marker in comment_markers(comments, limits)):
        return
    try:
        client.post_comment(issue_number, body)
    except AuditIssueError as write_error:
        for delay in CONFIRMATION_DELAYS:
            if delay:
                client.sleep(delay)
            try:
                if any(
                    marker.get("batch_id") == value
                    for marker in comment_markers(client.comments(issue_number), limits)
                ):
                    return
            except AuditIssueError:
                continue
        raise write_error


def reconcile_campaign(
    client: IssueClient,
    issue: dict[str, Any],
    state: dict[str, Any],
    report: dict[str, Any],
    report_md: str,
    current: dict[str, Any],
    workflow_url: str,
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    number = int(issue["number"])
    starting_state = state
    comments = client.comments(number)
    state, recovered = recover_from_comments(state, comments, limits)
    previous = state["applied"]
    transitioned = previous["semantic_digest"] != current["semantic_digest"]
    if previous["semantic_digest"] == current["semantic_digest"]:
        if recovered or previous["body_digest"] != current["body_digest"]:
            state = make_state(state["campaign"], state["sequence"], current, state["origin_semantic_digest"])
    else:
        sequence = int(state["sequence"]) + 1
        value = batch_id(state["campaign"], sequence, previous["semantic_digest"], current["semantic_digest"])
        comment = transition_comment(
            report,
            previous,
            current,
            state["campaign"],
            sequence,
            value,
            workflow_url,
            limits=limits,
        )
        next_state = make_state(state["campaign"], sequence, current, state["origin_semantic_digest"])
        managed_body(str(issue.get("body") or ""), report, report_md, next_state, workflow_url, limits)
        post_comment_once(client, number, comment, value, comments, limits)
        state = next_state
    latest = client.issue(number)
    latest_body = str(latest.get("body") or "")
    latest_state = parse_state(latest_body, limits)
    if latest_state is None or latest_state["campaign"] != state["campaign"]:
        raise AuditIssueError(f"Audit issue #{number} lost its current campaign state before update")
    if compact_json(latest_state) != compact_json(starting_state):
        if compact_json(latest_state) != compact_json(state):
            raise AuditIssueError(f"Audit issue #{number} changed concurrently before update")
        starting_state = latest_state
    body = managed_body(latest_body, report, report_md, state, workflow_url, limits)
    state_changed = compact_json(starting_state) != compact_json(state)
    if not transitioned and not recovered and not state_changed:
        if comparable_managed_body(latest_body) == comparable_managed_body(body):
            return latest, state, False
    return client.patch_issue(number, {"body": body}), state, True


def create_issue_safely(
    client: IssueClient,
    title: str,
    body: str,
    label: str,
    campaign: str,
    title_prefix: str,
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> dict[str, Any]:
    try:
        return client.create_issue(title, body, label)
    except AuditIssueError as write_error:
        for delay in CONFIRMATION_DELAYS:
            if delay:
                client.sleep(delay)
            try:
                match = find_campaign(audit_issues(client.issues(), title_prefix, limits), campaign)
                if match:
                    return match[0]
            except AuditIssueError:
                continue
        raise write_error


def close_old_campaigns(
    client: IssueClient,
    issues: list[tuple[dict[str, Any], dict[str, Any] | None]],
    current_campaign: str,
    current_issue_number: int | None,
    workflow_url: str,
    has_drift: bool,
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> bool:
    changed = False
    for issue, state in sorted(issues, key=lambda value: int(value[0].get("number", 0))):
        if (
            not state
            or state["campaign"] == current_campaign
            or issue.get("state") != "open"
            or issue.get("number") == current_issue_number
        ):
            continue
        number = int(issue["number"])
        value = sha256_json({"old": state["campaign"], "new": current_campaign, "type": "superseded"})
        suffix = "A new campaign tracks the remaining drift." if has_drift else "The new baseline is currently clean."
        message = f"The committed `spec.lock` baseline changed, so this audit campaign is superseded. {suffix}"
        post_comment_once(
            client,
            number,
            event_comment(state["campaign"], value, message, workflow_url),
            value,
            client.comments(number),
            limits,
        )
        client.patch_issue(number, {"state": "closed", "state_reason": "completed"})
        changed = True
    return changed


def verify_reconciliation_once(
    client: IssueClient,
    campaign: str,
    issue_number: int | None,
    expected_state: dict[str, Any] | None,
    title: str,
    title_prefix: str,
    label: str,
    has_drift: bool,
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> None:
    issue_values = audit_issues(client.issues(), title_prefix, limits)
    find_campaign(issue_values, campaign)
    obsolete = [
        issue
        for issue, state in issue_values
        if issue.get("state") == "open" and (state is None or state["campaign"] != campaign)
    ]
    if obsolete:
        numbers = ", ".join(f"#{issue.get('number')}" for issue in obsolete)
        raise AuditIssueError(f"Obsolete FLS audit issues remain open after reconciliation: {numbers}")

    if issue_number is None:
        if any(state and state["campaign"] == campaign for _, state in issue_values):
            raise AuditIssueError("Current FLS audit campaign exists unexpectedly after reconciliation")
        return
    if expected_state is None:
        raise AuditIssueError("Current FLS audit issue has no expected state")

    records = [issue for issue, _ in issue_values if int(issue.get("number", 0)) == issue_number]
    if len(records) != 1:
        raise AuditIssueError(f"Expected one current FLS audit issue #{issue_number}; found {len(records)}")
    issue = records[0]
    state = parse_state(str(issue.get("body") or ""), limits)
    if state is None or compact_json(state) != compact_json(expected_state):
        raise AuditIssueError(f"FLS audit issue #{issue_number} state does not match the reconciled report")
    if issue.get("title") != title or label not in issue_labels(issue):
        raise AuditIssueError(f"FLS audit issue #{issue_number} identity does not match the current campaign")
    expected_status = "open" if has_drift else "closed"
    if issue.get("state") != expected_status:
        raise AuditIssueError(f"FLS audit issue #{issue_number} is {issue.get('state')}; expected {expected_status}")


def verify_reconciliation(
    client: IssueClient,
    campaign: str,
    issue_number: int | None,
    expected_state: dict[str, Any] | None,
    title: str,
    title_prefix: str,
    label: str,
    has_drift: bool,
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> None:
    issue_error: Exception | None = None
    for delay in VERIFICATION_DELAYS:
        if delay:
            client.sleep(delay)
        try:
            verify_reconciliation_once(
                client,
                campaign,
                issue_number,
                expected_state,
                title,
                title_prefix,
                label,
                has_drift,
                limits,
            )
        except AuditIssueError as current_error:
            issue_error = current_error
            continue
        break
    else:
        assert issue_error is not None
        raise issue_error

    if issue_number is None:
        return
    assert expected_state is not None
    comment_error: Exception | None = None
    for delay in VERIFICATION_DELAYS:
        if delay:
            client.sleep(delay)
        try:
            verify_comment_history(expected_state, client.comments(issue_number), limits)
        except AuditIssueError as current_error:
            comment_error = current_error
            continue
        return
    assert comment_error is not None
    raise comment_error


def reconcile(
    client: IssueClient,
    report: dict[str, Any],
    report_md: str,
    spec_lock: dict[str, Any],
    label: str,
    title_prefix: str,
    workflow_url: str = "",
    *,
    limits: BodyLimits = DEFAULT_BODY_LIMITS,
) -> str:
    campaign = campaign_id(spec_lock)
    items = canonical_items(report)
    current = make_applied(report, report_md, items)
    title = expected_title(title_prefix, campaign)
    audit_issue_values = audit_issues(client.issues(), title_prefix, limits)
    match = find_campaign(audit_issue_values, campaign)
    damaged = [
        issue
        for issue, state in audit_issue_values
        if state is None and issue.get("state") != "closed"
    ]
    if damaged:
        numbers = ", ".join(f"#{issue.get('number')}" for issue in damaged)
        raise AuditIssueError(f"Non-closed bot-owned FLS audit issues have no valid campaign state: {numbers}")
    client.ensure_label(label)
    issue: dict[str, Any] | None = None
    state: dict[str, Any] | None = None
    changed = False

    if match:
        issue, state = match
        issue, identity_changed = refresh_issue_identity(client, issue, title, label)
        changed |= identity_changed
        if issue.get("state") == "closed" and items:
            issue = client.patch_issue(int(issue["number"]), {"state": "open"})
            changed = True
    elif items:
        state = make_state(campaign, 0, current)
        body = managed_body("", report, report_md, state, workflow_url, limits)
        issue = create_issue_safely(client, title, body, label, campaign, title_prefix, limits)
        parsed = parse_state(str(issue.get("body") or ""), limits)
        state = parsed or state
        changed = True

    if issue is not None and state is not None:
        issue, state, reconciled = reconcile_campaign(
            client, issue, state, report, report_md, current, workflow_url, limits
        )
        changed |= reconciled
        if not items and issue.get("state") == "open":
            issue = client.patch_issue(int(issue["number"]), {"state": "closed", "state_reason": "completed"})
            changed = True

    current_number = int(issue["number"]) if issue else None
    changed |= close_old_campaigns(
        client,
        audit_issue_values,
        campaign,
        current_number,
        workflow_url,
        bool(items),
        limits,
    )
    verify_reconciliation(
        client,
        campaign,
        current_number,
        state,
        title,
        title_prefix,
        label,
        bool(items),
        limits,
    )

    if issue is None:
        return "Reconciled old audit campaigns." if changed else "No changes found and no current campaign issue exists."
    return f"Reconciled audit issue #{issue['number']}." if changed else f"Audit issue #{issue['number']} is already current."
