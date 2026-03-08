from __future__ import annotations

from aiautomouse.engine.models import RetrySpec


def total_attempts(retry: RetrySpec | None) -> int:
    if retry is None:
        return 1
    return max(1, retry.attempts)


def should_retry(attempt_number: int, retry: RetrySpec | None) -> bool:
    return attempt_number < total_attempts(retry)

