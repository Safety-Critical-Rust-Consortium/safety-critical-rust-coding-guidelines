"""Deferred reconcile payload and identity helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DeferredPayloadKind(StrEnum):
    DEFERRED_COMMENT = "deferred_comment"
    DEFERRED_REVIEW_COMMENT = "deferred_review_comment"
    DEFERRED_REVIEW_SUBMITTED = "deferred_review_submitted"
    DEFERRED_REVIEW_DISMISSED = "deferred_review_dismissed"


@dataclass(frozen=True)
class DeferredArtifactIdentity:
    payload_kind: DeferredPayloadKind
    schema_version: int
    source_run_id: int
    source_run_attempt: int
    source_event_name: str
    source_event_action: str
    source_event_key: str
    pr_number: int


@dataclass(frozen=True)
class DeferredReviewPayload:
    identity: DeferredArtifactIdentity
    review_id: int
    source_submitted_at: str | None
    source_review_state: str | None
    source_commit_id: str | None
    actor_login: str | None
    raw_payload: dict

    @property
    def pr_number(self) -> int:
        return self.identity.pr_number


@dataclass(frozen=True)
class DeferredCommentPayload:
    identity: DeferredArtifactIdentity
    comment_id: int
    comment_body: str
    comment_created_at: str
    comment_author: str
    comment_author_id: int
    comment_user_type: str
    comment_sender_type: str
    comment_installation_id: str | None
    comment_performed_via_github_app: bool
    issue_author: str
    issue_state: str
    issue_labels: tuple[str, ...]
    raw_payload: dict

    @property
    def pr_number(self) -> int:
        return self.identity.pr_number


@dataclass(frozen=True)
class DeferredCommentReplayContext:
    payload: DeferredCommentPayload
    expected_event_name: str
    live_comment_endpoint: str

    @property
    def source_event_key(self) -> str:
        return self.payload.identity.source_event_key

    @property
    def comment_id(self) -> int:
        return self.payload.comment_id

    @property
    def pr_number(self) -> int:
        return self.payload.identity.pr_number

    @property
    def actor_login(self) -> str:
        return self.payload.comment_author

    @property
    def source_created_at(self) -> str:
        return self.payload.comment_created_at

    @property
    def source_freshness_eligible(self) -> bool:
        return True


@dataclass(frozen=True)
class DeferredReviewReplayContext:
    payload: DeferredReviewPayload

    @property
    def source_event_key(self) -> str:
        return self.payload.identity.source_event_key

    @property
    def review_id(self) -> int:
        return self.payload.review_id

    @property
    def pr_number(self) -> int:
        return self.payload.identity.pr_number

    @property
    def actor_login(self) -> str:
        return self.payload.actor_login or ""


def _build_deferred_identity(payload: dict) -> DeferredArtifactIdentity:
    try:
        resolved_payload_kind = DeferredPayloadKind(str(payload["payload_kind"]))
    except (KeyError, ValueError) as exc:
        raise RuntimeError("Unsupported deferred workflow_run payload") from exc
    return DeferredArtifactIdentity(
        payload_kind=resolved_payload_kind,
        schema_version=int(payload["schema_version"]),
        source_run_id=int(payload["source_run_id"]),
        source_run_attempt=int(payload["source_run_attempt"]),
        source_event_name=str(payload["source_event_name"]),
        source_event_action=str(payload["source_event_action"]),
        source_event_key=str(payload["source_event_key"]),
        pr_number=int(payload["pr_number"]),
    )


def build_deferred_comment_replay_context(
    payload: DeferredCommentPayload,
    *,
    expected_event_name: str,
    live_comment_endpoint: str,
) -> DeferredCommentReplayContext:
    if payload.identity.source_event_key != f"{expected_event_name}:{payload.comment_id}":
        raise RuntimeError("Deferred comment artifact source_event_key mismatch")
    return DeferredCommentReplayContext(
        payload=payload,
        expected_event_name=expected_event_name,
        live_comment_endpoint=live_comment_endpoint,
    )


def build_deferred_review_replay_context(
    payload: DeferredReviewPayload,
    *,
    expected_event_action: str,
) -> DeferredReviewReplayContext:
    expected_prefix = "pull_request_review:" if expected_event_action == "submitted" else "pull_request_review_dismissed:"
    if payload.identity.source_event_action != expected_event_action:
        raise RuntimeError("Deferred review artifact action mismatch")
    if payload.identity.source_event_key != f"{expected_prefix}{payload.review_id}":
        raise RuntimeError(f"Deferred review-{expected_event_action} artifact source_event_key mismatch")
    return DeferredReviewReplayContext(payload=payload)


def _validate_deferred_comment_artifact(payload: dict) -> None:
    required = {
        "payload_kind",
        "schema_version",
        "source_run_id",
        "source_run_attempt",
        "source_event_name",
        "source_event_action",
        "source_event_key",
        "pr_number",
        "comment_id",
        "comment_body",
        "comment_created_at",
        "comment_author",
        "comment_author_id",
        "comment_user_type",
        "comment_sender_type",
        "comment_performed_via_github_app",
        "issue_author",
        "issue_state",
        "issue_labels",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise RuntimeError("Deferred comment artifact missing required fields: " + ", ".join(missing))
    if payload.get("schema_version") != 3:
        raise RuntimeError("Deferred workflow_run payload schema_version is not accepted")
    if not isinstance(payload.get("comment_id"), int) or not isinstance(payload.get("pr_number"), int):
        raise RuntimeError("Deferred comment artifact comment_id and pr_number must be integers")
    if not isinstance(payload.get("comment_body"), str) or not isinstance(payload.get("comment_created_at"), str):
        raise RuntimeError("Deferred comment artifact comment body or timestamp is malformed")


def _validate_deferred_review_artifact(payload: dict) -> None:
    required = {
        "payload_kind",
        "schema_version",
        "source_run_id",
        "source_run_attempt",
        "source_event_name",
        "source_event_action",
        "source_event_key",
        "pr_number",
        "review_id",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise RuntimeError("Deferred review artifact missing required fields: " + ", ".join(missing))
    if payload.get("schema_version") != 3:
        raise RuntimeError("Deferred workflow_run payload schema_version is not accepted")
    if not isinstance(payload.get("review_id"), int) or not isinstance(payload.get("pr_number"), int):
        raise RuntimeError("Deferred review artifact review_id and pr_number must be integers")


def _validate_deferred_review_comment_artifact(payload: dict) -> None:
    _validate_deferred_comment_artifact(payload)


def parse_deferred_context_payload(payload: dict) -> DeferredReviewPayload | DeferredCommentPayload:
    if not isinstance(payload, dict):
        raise RuntimeError("Deferred context payload must be a JSON object")
    if payload.get("schema_version") != 3:
        raise RuntimeError("Deferred workflow_run payload schema_version is not accepted")
    identity = _build_deferred_identity(payload)
    if identity.payload_kind == DeferredPayloadKind.DEFERRED_COMMENT or identity.payload_kind == DeferredPayloadKind.DEFERRED_REVIEW_COMMENT:
        _validate_deferred_review_comment_artifact(payload)
        return DeferredCommentPayload(
            identity=identity,
            comment_id=int(payload["comment_id"]),
            comment_body=str(payload["comment_body"]),
            comment_created_at=str(payload["comment_created_at"]),
            comment_author=str(payload["comment_author"]),
            comment_author_id=int(payload["comment_author_id"]),
            comment_user_type=str(payload["comment_user_type"]),
            comment_sender_type=str(payload["comment_sender_type"]),
            comment_installation_id=(str(payload["comment_installation_id"]) if payload.get("comment_installation_id") else None),
            comment_performed_via_github_app=bool(payload["comment_performed_via_github_app"]),
            issue_author=str(payload["issue_author"]),
            issue_state=str(payload["issue_state"]),
            issue_labels=tuple(str(label) for label in payload["issue_labels"]),
            raw_payload=payload,
        )
    if identity.payload_kind == DeferredPayloadKind.DEFERRED_REVIEW_SUBMITTED or identity.payload_kind == DeferredPayloadKind.DEFERRED_REVIEW_DISMISSED:
        _validate_deferred_review_artifact(payload)
        return DeferredReviewPayload(
            identity=identity,
            review_id=int(payload["review_id"]),
            source_submitted_at=(str(payload["source_submitted_at"]) if payload.get("source_submitted_at") is not None else None),
            source_review_state=(str(payload["source_review_state"]) if payload.get("source_review_state") is not None else None),
            source_commit_id=(str(payload["source_commit_id"]) if payload.get("source_commit_id") is not None else None),
            actor_login=(str(payload["actor_login"]) if payload.get("actor_login") is not None else None),
            raw_payload=payload,
        )
    raise RuntimeError("Unsupported deferred workflow_run payload")


def validate_triggering_run_identity(bot, payload: dict) -> None:
    triggering_id = bot.get_config_value("WORKFLOW_RUN_TRIGGERING_ID").strip()
    if triggering_id and str(payload.get("source_run_id")) != triggering_id:
        raise RuntimeError("Deferred artifact run_id mismatch")
    triggering_attempt = bot.get_config_value("WORKFLOW_RUN_TRIGGERING_ATTEMPT").strip()
    if triggering_attempt and str(payload.get("source_run_attempt")) != triggering_attempt:
        raise RuntimeError("Deferred artifact run_attempt mismatch")
    if bot.get_config_value("WORKFLOW_RUN_TRIGGERING_CONCLUSION").strip() != "success":
        raise RuntimeError("Triggering observer workflow did not conclude successfully")


def validate_workflow_run_artifact_identity(bot, payload: dict) -> None:
    validate_triggering_run_identity(bot, payload)
