"""
Production Data Hub - Performance Metrics

Lightweight in-process query performance monitor.
Records duration, row count, and cache-hit status for named query groups,
keeping a bounded rolling window per group. Thread-safe.

Exposed via /metrics/performance and /metrics/cache endpoints.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict


@dataclass
class QueryMetric:
    query_name: str
    duration_ms: float
    row_count: int
    cache_hit: bool
    timestamp: float = field(default_factory=time.time)


class PerformanceMonitor:
    """Bounded rolling-window query metrics, thread-safe."""

    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self._metrics: Dict[str, Deque[QueryMetric]] = defaultdict(
            lambda: deque(maxlen=max_samples)
        )
        self._lock = threading.Lock()

    def record(
        self,
        query_name: str,
        duration_ms: float,
        row_count: int = 0,
        cache_hit: bool = False,
    ) -> None:
        metric = QueryMetric(
            query_name=query_name,
            duration_ms=float(duration_ms),
            row_count=int(row_count),
            cache_hit=bool(cache_hit),
        )
        with self._lock:
            self._metrics[query_name].append(metric)

    def _stats_for(self, samples: Deque[QueryMetric]) -> dict:
        if not samples:
            return {}
        durations = sorted(m.duration_ms for m in samples)
        n = len(durations)

        def pct(p: float) -> float:
            if n == 1:
                return durations[0]
            idx = min(n - 1, max(0, int(round((n - 1) * p))))
            return durations[idx]

        cache_hits = sum(1 for m in samples if m.cache_hit)
        total_rows = sum(m.row_count for m in samples)
        return {
            "count": n,
            "avg_ms": round(sum(durations) / n, 2),
            "p50_ms": round(pct(0.50), 2),
            "p95_ms": round(pct(0.95), 2),
            "p99_ms": round(pct(0.99), 2),
            "max_ms": round(durations[-1], 2),
            "cache_hit_rate": round(cache_hits / n * 100, 1),
            "avg_rows": round(total_rows / n, 1),
        }

    def get_stats(self, query_name: str) -> dict:
        with self._lock:
            samples = list(self._metrics.get(query_name, ()))
        return self._stats_for(deque(samples))

    def get_all_stats(self) -> Dict[str, dict]:
        with self._lock:
            snapshot = {name: list(dq) for name, dq in self._metrics.items()}
        return {name: self._stats_for(deque(s)) for name, s in snapshot.items()}

    def reset(self) -> None:
        with self._lock:
            self._metrics.clear()


performance_monitor = PerformanceMonitor()


class TimedQuery:
    """Context manager that records duration into performance_monitor on exit.

    Usage:
        with TimedQuery("records") as t:
            rows = _run_query(...)
            t.row_count = len(rows)
            t.cache_hit = False
    """

    def __init__(self, query_name: str, cache_hit: bool = False):
        self.query_name = query_name
        self.row_count = 0
        self.cache_hit = cache_hit
        self._t0 = 0.0

    def __enter__(self) -> "TimedQuery":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        duration_ms = (time.perf_counter() - self._t0) * 1000
        performance_monitor.record(
            self.query_name,
            duration_ms=duration_ms,
            row_count=self.row_count,
            cache_hit=self.cache_hit,
        )
