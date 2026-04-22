import pytest

from todo_api.rate_limit import TokenBucket


def test_fresh_bucket_allows_capacity_requests() -> None:
    bucket = TokenBucket(capacity=5, refill_rate_per_second=1.0)
    for _ in range(5):
        assert bucket.consume(now=0.0) is True


def test_bucket_denies_when_exhausted() -> None:
    bucket = TokenBucket(capacity=5, refill_rate_per_second=1.0)
    for _ in range(5):
        bucket.consume(now=0.0)
    assert bucket.consume(now=0.0) is False


def test_bucket_refills_over_time() -> None:
    bucket = TokenBucket(capacity=5, refill_rate_per_second=1.0)
    for _ in range(5):
        bucket.consume(now=0.0)
    assert bucket.consume(now=0.0) is False
    assert bucket.consume(now=1.0) is True


def test_bucket_refill_caps_at_capacity() -> None:
    bucket = TokenBucket(capacity=5, refill_rate_per_second=1.0)
    bucket.consume(1, now=0.0)
    results = []
    for i in range(6):
        results.append(bucket.consume(now=10.0 + i * 0.001))
    assert results.count(True) == 5
    assert results[5] is False


def test_consume_n() -> None:
    bucket = TokenBucket(capacity=5, refill_rate_per_second=1.0)
    assert bucket.consume(3, now=0.0) is True
    assert bucket.consume(3, now=0.0) is False


def test_consume_negative_raises() -> None:
    bucket = TokenBucket(capacity=5, refill_rate_per_second=1.0)
    with pytest.raises(ValueError):
        bucket.consume(-1)
    with pytest.raises(ValueError):
        bucket.consume(0)
