"""Shared retry helpers for reviewer-bot transport and state workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

RETRY_POLICY_NONE = "none"
RETRY_POLICY_IDEMPOTENT_READ = "idempotent_read"


class JitterSource(Protocol):
    def uniform(self, lower: float, upper: float) -> float: ...


@dataclass(frozen=True)
class RetrySpec:
    retry_policy: str
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float = 8.0


def is_retryable_status(status_code: int | None) -> bool:
    return status_code == 429 or (status_code is not None and status_code >= 500)


def is_rate_limited_response(
    status_code: int | None,
    *,
    headers: dict[str, str] | None = None,
    text: str = "",
) -> bool:
    if status_code == 429:
        return True
    if status_code != 403:
        return False
    normalized_headers = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    if "retry-after" in normalized_headers:
        return True
    if normalized_headers.get("x-ratelimit-remaining", "").strip() == "0":
        return True
    return "rate limit" in text.lower()


def retry_delay_seconds(
    base_delay_seconds: float,
    retry_attempt: int,
    *,
    jitter: JitterSource,
    status_code: int | None = None,
    headers: dict[str, str] | None = None,
    text: str = "",
    now: datetime | None = None,
    max_delay_seconds: float = 8.0,
) -> float:
    normalized_headers = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    retry_after = normalized_headers.get("retry-after", "").strip()
    if is_rate_limited_response(status_code, headers=normalized_headers, text=text) and retry_after:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    if (
        is_rate_limited_response(status_code, headers=normalized_headers, text=text)
        and normalized_headers.get("x-ratelimit-remaining", "").strip() == "0"
    ):
        reset_at = normalized_headers.get("x-ratelimit-reset", "").strip()
        if reset_at:
            try:
                reset_epoch = float(reset_at)
            except ValueError:
                pass
            else:
                reference_now = now or datetime.now(timezone.utc)
                return max(reset_epoch - reference_now.timestamp(), 0.0)
    return bounded_exponential_delay(
        base_delay_seconds,
        retry_attempt,
        jitter=jitter,
        max_delay_seconds=max_delay_seconds,
    )


def additional_attempts_for_policy(retry_policy: str, retry_limit: int) -> int:
    if retry_policy == RETRY_POLICY_NONE:
        return 0
    if retry_policy == RETRY_POLICY_IDEMPOTENT_READ:
        return retry_limit
    raise ValueError(f"Unsupported retry policy: {retry_policy}")


def max_attempts_for_policy(retry_policy: str, retry_limit: int) -> int:
    return 1 + additional_attempts_for_policy(retry_policy, retry_limit)


def bounded_exponential_delay(
    base_delay_seconds: float,
    retry_attempt: int,
    *,
    jitter: JitterSource,
    max_delay_seconds: float = 8.0,
) -> float:
    bounded_base = min(base_delay_seconds * (2 ** max(retry_attempt - 1, 0)), max_delay_seconds)
    return bounded_base + jitter.uniform(0, bounded_base)
