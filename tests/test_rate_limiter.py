# tests/test_rate_limiter.py
"""
Rate Limiter Unit Tests

Tests for the sliding window rate limiting implementation.

rate-limiter-clock-injection (2026-06-12): time.sleep-based window tests were
converted to a FakeClock driven via the RateLimiter `clock` parameter — zero
real sleeps, deterministic on loaded CI runners.
"""

import pytest

from shared.rate_limiter import RateLimiter


class FakeClock:
    """Manually-advanced time source for deterministic window tests."""

    def __init__(self, start: float = 1000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, sec: float) -> None:
        self.t += sec


class TestRateLimiterBasic:
    """기본 RateLimiter 기능 테스트"""

    def test_is_allowed_under_limit(self):
        """한도 내 요청은 허용되어야 함"""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        for _ in range(5):
            assert limiter.is_allowed("192.168.1.1") is True

    def test_is_allowed_exceeds_limit(self):
        """한도 초과 요청은 거부되어야 함"""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        # 3번은 허용
        for _ in range(3):
            assert limiter.is_allowed("10.0.0.1") is True

        # 4번째는 거부
        assert limiter.is_allowed("10.0.0.1") is False

    def test_different_ips_independent(self):
        """서로 다른 IP는 독립적으로 카운트됨"""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        # IP 1: 2회 허용
        assert limiter.is_allowed("192.168.1.1") is True
        assert limiter.is_allowed("192.168.1.1") is True
        assert limiter.is_allowed("192.168.1.1") is False  # 3회 차단

        # IP 2: 여전히 2회 허용
        assert limiter.is_allowed("192.168.1.2") is True
        assert limiter.is_allowed("192.168.1.2") is True
        assert limiter.is_allowed("192.168.1.2") is False


class TestRateLimiterRemaining:
    """remaining() 메서드 테스트"""

    def test_remaining_initial(self):
        """초기 remaining은 max_requests와 동일"""
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        assert limiter.remaining("192.168.1.1") == 10

    def test_remaining_after_requests(self):
        """요청 후 remaining 감소"""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        limiter.is_allowed("10.0.0.1")
        assert limiter.remaining("10.0.0.1") == 4

        limiter.is_allowed("10.0.0.1")
        assert limiter.remaining("10.0.0.1") == 3

    def test_remaining_zero_when_exceeded(self):
        """한도 초과 시 remaining은 0"""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        limiter.is_allowed("10.0.0.1")
        limiter.is_allowed("10.0.0.1")
        limiter.is_allowed("10.0.0.1")  # 거부되지만 기록됨

        # remaining은 0이어야 함
        assert limiter.remaining("10.0.0.1") == 0

    def test_remaining_does_not_record(self):
        """remaining() 호출은 요청을 기록하지 않음"""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        # remaining 조회 (요청 기록 안됨)
        assert limiter.remaining("10.0.0.1") == 3

        # 여전히 3회 허용
        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.1") is True


class TestRateLimiterRetryAfter:
    """retry_after() 메서드 테스트"""

    def test_retry_after_zero_when_allowed(self):
        """허용된 요청에 대한 retry_after는 0"""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        limiter.is_allowed("192.168.1.1")
        # 아직 한도 내이므로 0 또는 작은 값
        retry = limiter.retry_after("192.168.1.1")
        # 실제로는 가장 오래된 요청 기준이므로 window 초과 시간
        # 하지만 한도 내에서는 의미 없음
        assert retry >= 0

    def test_retry_after_returns_positive_when_exceeded(self):
        """한도 초과 시 retry_after는 양수"""
        limiter = RateLimiter(max_requests=1, window_seconds=60)

        limiter.is_allowed("10.0.0.1")
        limiter.is_allowed("10.0.0.1")  # 거부

        retry = limiter.retry_after("10.0.0.1")
        assert retry > 0
        assert retry <= 60


class TestRateLimiterSlidingWindow:
    """슬라이딩 윈도우 동작 테스트"""

    def test_window_expiration(self):
        """윈도우 만료 후 요청 재허용"""
        clock = FakeClock()
        limiter = RateLimiter(max_requests=2, window_seconds=1, clock=clock)

        # 2회 사용
        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.1") is False

        # 윈도우 만료
        clock.advance(1.1)

        # 다시 허용
        assert limiter.is_allowed("10.0.0.1") is True

    def test_window_expiration_boundary(self):
        """정확히 window_seconds 경과 시점에 만료(<= cutoff)되어 재허용"""
        clock = FakeClock()
        limiter = RateLimiter(max_requests=1, window_seconds=1, clock=clock)

        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.1") is False

        # 경계: 정확히 1.0초 경과 — timestamps[0] <= cutoff 이므로 만료
        clock.advance(1.0)
        assert limiter.is_allowed("10.0.0.1") is True

    def test_partial_window_expiration(self):
        """부분적 윈도우 만료로 슬롯 확보"""
        clock = FakeClock()
        limiter = RateLimiter(max_requests=3, window_seconds=2, clock=clock)

        # 3회 사용 (첫 요청만 0.5초 먼저)
        limiter.is_allowed("10.0.0.1")
        clock.advance(0.5)
        limiter.is_allowed("10.0.0.1")
        limiter.is_allowed("10.0.0.1")

        # 한도 초과
        assert limiter.is_allowed("10.0.0.1") is False

        # 첫 번째 요청만 만료되는 시점까지 진행 (총 2.1초 > window 2초)
        clock.advance(1.6)

        # 첫 번째 요청 만료로 슬롯 1개 확보
        assert limiter.is_allowed("10.0.0.1") is True


class TestRateLimiterCleanup:
    """cleanup() 메서드 테스트"""

    def test_cleanup_removes_expired_ips(self):
        """만료된 IP 항목 제거"""
        clock = FakeClock()
        limiter = RateLimiter(max_requests=5, window_seconds=1, clock=clock)

        # 여러 IP에서 요청
        limiter.is_allowed("10.0.0.1")
        limiter.is_allowed("10.0.0.2")
        limiter.is_allowed("10.0.0.3")

        # 윈도우 만료
        clock.advance(1.1)

        # cleanup 실행
        removed = limiter.cleanup()
        assert removed == 3

    def test_cleanup_max_ips_bounds_scan(self):
        """max_ips는 스캔 자체를 제한한다 — 과거엔 removed(스캔 중 항상 0)를
        검사해 가드가 절대 발동하지 않았다 (full-review-202607)."""
        clock = FakeClock()
        limiter = RateLimiter(max_requests=5, window_seconds=1, clock=clock)
        for i in range(10):
            limiter.is_allowed(f"10.0.1.{i}")
        clock.advance(1.1)

        # 만료 IP 10개 중 스캔 상한 3개까지만 제거
        assert limiter.cleanup(max_ips=3) == 3
        # 다음 호출이 이어서 정리
        assert limiter.cleanup() == 7

    def test_cleanup_keeps_active_ips(self):
        """활성 IP는 유지됨"""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        # 활성 요청
        limiter.is_allowed("10.0.0.1")

        # 만료된 요청
        clock2 = FakeClock()
        limiter2 = RateLimiter(max_requests=5, window_seconds=1, clock=clock2)
        limiter2.is_allowed("10.0.0.2")
        clock2.advance(1.1)
        limiter2.cleanup()

        # 활성 IP는 여전히 기록됨
        assert limiter.remaining("10.0.0.1") == 4


class TestRateLimiterStats:
    """get_stats() 메서드 테스트"""

    def test_stats_initial(self):
        """초기 상태 통계"""
        limiter = RateLimiter(max_requests=10, window_seconds=30)
        stats = limiter.get_stats()

        assert stats["active_ips"] == 0
        assert stats["total_tracked_requests"] == 0
        assert stats["max_requests_per_window"] == 10
        assert stats["window_seconds"] == 30

    def test_stats_after_requests(self):
        """요청 후 통계 업데이트"""
        limiter = RateLimiter(max_requests=10, window_seconds=60)

        limiter.is_allowed("10.0.0.1")
        limiter.is_allowed("10.0.0.1")
        limiter.is_allowed("10.0.0.2")

        stats = limiter.get_stats()

        assert stats["active_ips"] == 2
        assert stats["total_tracked_requests"] == 3


class TestRateLimiterThreadSafety:
    """스레드 안전성 테스트"""

    def test_concurrent_requests(self):
        """동시 요청 처리 테스트"""
        import threading

        limiter = RateLimiter(max_requests=100, window_seconds=60)
        success_count = 0
        lock = threading.Lock()

        def make_request():
            nonlocal success_count
            if limiter.is_allowed("10.0.0.1"):
                with lock:
                    success_count += 1

        threads = [threading.Thread(target=make_request) for _ in range(150)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 정확히 100개만 성공해야 함
        assert success_count == 100
