from __future__ import annotations

import math
import time

from fastapi import Depends, HTTPException, Request

from todo_api.auth import get_current_user


class TokenBucket:
    def __init__(self, capacity: int, refill_rate_per_second: float) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate_per_second
        self.tokens = float(capacity)
        self._last_refill: float | None = None

    def consume(self, n: int = 1, now: float | None = None) -> bool:
        if n <= 0:
            raise ValueError("n must be a positive integer")
        if now is None:
            now = time.monotonic()
        if self._last_refill is not None:
            elapsed = now - self._last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self._last_refill = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


_buckets: dict[str, TokenBucket] = {}


def _get_bucket(key: str, capacity: int, refill_rate: float) -> TokenBucket:
    if key not in _buckets:
        _buckets[key] = TokenBucket(capacity, refill_rate)
    return _buckets[key]


def reset_buckets() -> None:
    _buckets.clear()


_AUTHED_CAPACITY = 60
_AUTHED_REFILL = 1.0
_ANON_CAPACITY = 10
_ANON_REFILL = 10.0 / 60.0


def _retry_after(refill_rate: float) -> str:
    return str(max(1, math.ceil(1 / refill_rate)))


def authed_rate_limit(user_id: int = Depends(get_current_user)) -> int:
    bucket = _get_bucket(f"user:{user_id}", _AUTHED_CAPACITY, _AUTHED_REFILL)
    if not bucket.consume():
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": _retry_after(_AUTHED_REFILL)},
        )
    return user_id


def anon_rate_limit(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    bucket = _get_bucket(f"ip:{host}", _ANON_CAPACITY, _ANON_REFILL)
    if not bucket.consume():
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": _retry_after(_ANON_REFILL)},
        )
    return host
