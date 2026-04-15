# Database Performance Optimization Design Document

> **Feature**: DB Performance Optimization
> **Status**: Design
> **Priority**: High
> **Created**: 2026-02-25
> **Based on**: db-performance-optimization.plan.md

---

## 1. Architecture Overview

### 1.1 Current Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer                            │
│  api/main.py, api/chat.py, api/tools.py               │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│                 Cache Layer                             │
│  shared/cache.py (TTLCache with mtime invalidation)    │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│               Database Router                           │
│  shared/database.py (DBRouter, DBTargets)              │
└─────────────────┬───────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
┌───────────────┐   ┌───────────────┐
│ production_   │   │ archive_2025  │
│ analysis.db   │   │     .db       │
│ (2026+ data)  │   │ (pre-2026)    │
└───────────────┘   └───────────────┘
```

### 1.2 Optimized Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer                            │
│  api/main.py, api/chat.py, api/tools.py               │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│            Enhanced Cache Layer (NEW)                   │
│  - Stale-while-revalidate                              │
│  - Smart invalidation with hash                         │
│  - Pre-computed aggregations                            │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│          Optimized Database Router                      │
│  - WAL mode enabled                                     │
│  - Connection pooling                                   │
│  - Query plan caching                                   │
└─────────────────┬───────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
┌───────────────┐   ┌───────────────┐
│ production_   │   │ archive_2025  │
│ analysis.db   │   │     .db       │
│ (Optimized)   │   │ (Optimized)   │
│ + Indexes     │   │ + Indexes     │
│ + WAL         │   │ + WAL         │
└───────────────┘   └───────────────┘
```

---

## 2. Index Design

### 2.1 Current Indexes

```sql
-- Existing indexes (if any)
-- Primary key on id (implicit)
```

### 2.2 New Indexes to Add

```sql
-- Index 1: Composite index for date range + item queries
-- Most common query pattern
CREATE INDEX IF NOT EXISTS idx_production_date_item
ON production_records(production_date, item_code);

-- Index 2: Lot number prefix search
-- For lot_number LIKE 'ABC%' queries
CREATE INDEX IF NOT EXISTS idx_lot_number
ON production_records(lot_number);

-- Index 3: Covering index for aggregations
-- Avoids table lookups for common aggregations
CREATE INDEX IF NOT EXISTS idx_agg_covering
ON production_records(item_code, production_date, good_quantity);

-- Index 4: Item name search (optional, if needed)
-- For item_name LIKE '%keyword%' - limited benefit due to leading wildcard
-- Consider using FTS5 instead for full-text search
```

### 2.3 Index Analysis Script

```python
# tools/analyze_indexes.py
import sqlite3
from pathlib import Path

def analyze_index_usage(db_path: Path) -> dict:
    """Analyze which indexes are actually used."""
    conn = sqlite3.connect(db_path)

    # Enable statistics
    conn.execute("PRAGMA stats = ON")

    # Run representative queries
    queries = [
        "SELECT * FROM production_records WHERE production_date >= '2026-01-01' LIMIT 100",
        "SELECT item_code, SUM(good_quantity) FROM production_records GROUP BY item_code",
        "SELECT * FROM production_records WHERE lot_number LIKE 'ABC%' LIMIT 100",
    ]

    results = {}
    for q in queries:
        plan = conn.execute(f"EXPLAIN QUERY PLAN {q}").fetchall()
        results[q[:50]] = plan

    return results

def get_index_stats(db_path: Path) -> list:
    """Get index usage statistics."""
    conn = sqlite3.connect(db_path)
    return conn.execute("""
        SELECT name, tbl_name, sql
        FROM sqlite_master
        WHERE type = 'index' AND sql IS NOT NULL
    """).fetchall()
```

---

## 3. Query Optimization

### 3.1 UNION ALL Optimization

**Current (Sequential):**
```python
# Both queries run sequentially
sql = """
    SELECT ... FROM archive.production_records WHERE ...
    UNION ALL
    SELECT ... FROM production_records WHERE ...
"""
```

**Optimized (Parallel + Early Termination):**
```python
# shared/database.py - Enhanced query execution

import concurrent.futures
from typing import List, Dict, Any

class ParallelQueryExecutor:
    """Execute UNION queries in parallel."""

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def execute_union_parallel(
        self,
        query_parts: List[str],
        params_list: List[list],
        conn_factory: callable
    ) -> List[Dict]:
        """Execute UNION parts in parallel and merge results."""
        results = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = []
            for query, params in zip(query_parts, params_list):
                future = executor.submit(
                    self._execute_single,
                    query, params, conn_factory
                )
                futures.append(future)

            for future in concurrent.futures.as_completed(futures, timeout=self.timeout):
                try:
                    results.extend(future.result())
                except Exception as e:
                    logger.warning(f"Query part failed: {e}")

        return results

    def _execute_single(self, query: str, params: list, conn_factory) -> List[Dict]:
        """Execute single query part."""
        with conn_factory() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
```

### 3.2 Aggregation Query Optimization

**Current:**
```python
# Aggregation after UNION (slow for large datasets)
sql = """
    SELECT item_code, SUM(good_quantity)
    FROM (
        SELECT ... FROM archive.production_records
        UNION ALL
        SELECT ... FROM production_records
    )
    GROUP BY item_code
"""
```

**Optimized (Pre-aggregation):**
```python
# Pre-aggregate in each DB, then merge
sql = """
    SELECT item_code, SUM(total) as total
    FROM (
        SELECT item_code, SUM(good_quantity) as total
        FROM archive.production_records
        WHERE ...
        GROUP BY item_code
        UNION ALL
        SELECT item_code, SUM(good_quantity) as total
        FROM production_records
        WHERE ...
        GROUP BY item_code
    )
    GROUP BY item_code
"""
```

---

## 4. Caching Enhancement

### 4.1 Smart Cache Invalidation

**Current (mtime-based):**
```python
# Invalidates on any DB file change
def get_db_version() -> str:
    return f"{live_mtime}_{archive_mtime}"
```

**Enhanced (Hash-based + mtime):**
```python
# shared/cache.py - Enhanced

import hashlib
from typing import Optional
from dataclasses import dataclass
import threading

@dataclass
class CacheInvalidationInfo:
    """Track what data changed for granular invalidation."""
    live_mtime: float
    archive_mtime: float
    live_row_count: int
    archive_row_count: int
    last_modified_date: str  # Most recent production_date

class SmartCacheManager:
    """Enhanced cache with granular invalidation."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._invalidation_info: Optional[CacheInvalidationInfo] = None
        self._lock = threading.Lock()

    def get_invalidation_key(self, query_type: str, params: dict) -> str:
        """Generate granular cache key based on what data affects the query."""
        info = self._get_invalidation_info()

        # Different query types are affected by different changes
        if query_type in ("monthly_total", "monthly_by_item"):
            # Only affected by changes in the queried date range
            date_range = f"{params.get('date_from', '')}_{params.get('date_to', '')}"
            return f"{query_type}_{date_range}_{info.last_modified_date}"
        else:
            # Full invalidation for other queries
            return f"{query_type}_{info.live_mtime}_{info.archive_mtime}"

    def _get_invalidation_info(self) -> CacheInvalidationInfo:
        """Get current invalidation info, cached for 1 second."""
        # Implementation similar to existing get_db_version but with more info
        pass
```

### 4.2 Stale-While-Revalidate Pattern

```python
# shared/cache.py

from typing import Callable, TypeVar, Optional
from dataclasses import dataclass
from datetime import datetime
import threading

T = TypeVar('T')

@dataclass
class CacheEntry:
    value: Any
    cached_at: datetime
    stale_at: datetime
    expires_at: datetime

class StaleWhileRevalidate:
    """Serve stale data while refreshing in background."""

    def __init__(
        self,
        stale_ttl: int = 240,  # 4 minutes - serve stale data
        expire_ttl: int = 300,  # 5 minutes - force refresh
    ):
        self.stale_ttl = stale_ttl
        self.expire_ttl = expire_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._refreshing: Set[str] = set()
        self._lock = threading.Lock()

    def get_or_fetch(
        self,
        key: str,
        fetch_func: Callable[[], T]
    ) -> T:
        """Get from cache or fetch, serving stale while refreshing."""
        now = datetime.now()

        with self._lock:
            entry = self._cache.get(key)

            # No cache entry - fetch synchronously
            if entry is None:
                return self._fetch_and_cache(key, fetch_func)

            # Not expired - return cached
            if now < entry.stale_at:
                return entry.value

            # Expired - must fetch synchronously
            if now >= entry.expires_at:
                return self._fetch_and_cache(key, fetch_func)

            # Stale but not expired - return stale, trigger background refresh
            if key not in self._refreshing:
                self._refreshing.add(key)
                threading.Thread(
                    target=self._background_refresh,
                    args=(key, fetch_func),
                    daemon=True
                ).start()

            return entry.value

    def _fetch_and_cache(self, key: str, fetch_func: Callable[[], T]) -> T:
        """Fetch data and cache it."""
        now = datetime.now()
        value = fetch_func()

        with self._lock:
            self._cache[key] = CacheEntry(
                value=value,
                cached_at=now,
                stale_at=now + timedelta(seconds=self.stale_ttl),
                expires_at=now + timedelta(seconds=self.expire_ttl)
            )

        return value

    def _background_refresh(self, key: str, fetch_func: Callable[[], T]) -> None:
        """Refresh cache in background."""
        try:
            self._fetch_and_cache(key, fetch_func)
        finally:
            with self._lock:
                self._refreshing.discard(key)
```

---

## 5. SQLite Configuration

### 5.1 WAL Mode Setup

```python
# shared/database.py - Enhanced

def init_db_pragmas(conn: sqlite3.Connection) -> None:
    """Apply optimized SQLite settings."""
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")

    # Larger cache (negative = KB)
    conn.execute("PRAGMA cache_size=-64000")  # 64MB

    # Memory-mapped I/O for read performance
    conn.execute("PRAGMA mmap_size=268435456")  # 256MB

    # Busy timeout for write conflicts
    conn.execute("PRAGMA busy_timeout=5000")  # 5 seconds

    # Synchronous mode (NORMAL is safe with WAL)
    conn.execute("PRAGMA synchronous=NORMAL")

    # Temp store in memory
    conn.execute("PRAGMA temp_store=MEMORY")

    logger.debug("SQLite PRAGMA settings applied")
```

### 5.2 Connection Pool Enhancement

```python
# shared/database.py

from contextlib import contextmanager
import threading
from queue import Queue, Empty

class ConnectionPool:
    """Simple connection pool for read-only connections."""

    def __init__(self, db_path: Path, pool_size: int = 5):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: Queue = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._initialized = False

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new connection with optimized settings."""
        db_uri = f"file:{self.db_path.absolute()}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        init_db_pragmas(conn)
        return conn

    def initialize(self) -> None:
        """Pre-create connections."""
        with self._lock:
            if self._initialized:
                return
            for _ in range(self.pool_size):
                self._pool.put(self._create_connection())
            self._initialized = True

    @contextmanager
    def get_connection(self):
        """Get connection from pool."""
        try:
            conn = self._pool.get(timeout=5.0)
        except Empty:
            # Pool exhausted, create temporary connection
            conn = self._create_connection()
            temporary = True
        else:
            temporary = False

        try:
            yield conn
        finally:
            if temporary:
                conn.close()
            else:
                self._pool.put(conn)
```

---

## 6. Monitoring & Metrics

### 6.1 Query Performance Metrics

```python
# shared/metrics.py (NEW)

from dataclasses import dataclass, field
from typing import Dict, List
from collections import defaultdict
import time
import threading

@dataclass
class QueryMetric:
    query_name: str
    duration_ms: float
    row_count: int
    cache_hit: bool
    timestamp: float = field(default_factory=time.time)

class PerformanceMonitor:
    """Track query performance metrics."""

    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self._metrics: Dict[str, List[QueryMetric]] = defaultdict(list)
        self._lock = threading.Lock()

    def record(self, metric: QueryMetric) -> None:
        """Record a query metric."""
        with self._lock:
            metrics = self._metrics[metric.query_name]
            metrics.append(metric)
            # Keep only last N samples
            if len(metrics) > self.max_samples:
                self._metrics[metric.query_name] = metrics[-self.max_samples:]

    def get_stats(self, query_name: str) -> Dict:
        """Get statistics for a query."""
        with self._lock:
            metrics = self._metrics.get(query_name, [])

        if not metrics:
            return {}

        durations = [m.duration_ms for m in metrics]
        cache_hits = sum(1 for m in metrics if m.cache_hit)

        return {
            "count": len(metrics),
            "avg_ms": sum(durations) / len(durations),
            "p50_ms": sorted(durations)[len(durations) // 2],
            "p99_ms": sorted(durations)[int(len(durations) * 0.99)],
            "cache_hit_rate": cache_hits / len(metrics) * 100,
        }

    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all queries."""
        with self._lock:
            return {name: self.get_stats(name) for name in self._metrics}

# Global instance
performance_monitor = PerformanceMonitor()
```

### 6.2 API Endpoint for Metrics

```python
# api/main.py - Add endpoint

@app.get("/metrics/performance")
def get_performance_metrics():
    """Get query performance metrics."""
    return performance_monitor.get_all_stats()

@app.get("/metrics/cache")
def get_cache_metrics():
    """Get cache statistics."""
    return {
        "api_cache": get_cache_stats(),
        "performance": performance_monitor.get_all_stats()
    }
```

---

## 7. Migration Script

### 7.1 Index Creation Script

```python
# tools/create_indexes.py

import sqlite3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import DB_FILE, ARCHIVE_DB_FILE
from shared.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

INDEXES = [
    ("idx_production_date_item", "production_records(production_date, item_code)"),
    ("idx_lot_number", "production_records(lot_number)"),
    ("idx_agg_covering", "production_records(item_code, production_date, good_quantity)"),
]

def create_indexes(db_path: Path, dry_run: bool = False) -> None:
    """Create indexes on database."""
    logger.info(f"Creating indexes on {db_path}")

    conn = sqlite3.connect(db_path)

    for index_name, index_def in INDEXES:
        sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {index_def}"

        if dry_run:
            logger.info(f"[DRY RUN] Would execute: {sql}")
        else:
            try:
                conn.execute(sql)
                logger.info(f"Created index: {index_name}")
            except Exception as e:
                logger.error(f"Failed to create index {index_name}: {e}")

    if not dry_run:
        conn.commit()
        # Analyze to update statistics
        conn.execute("ANALYZE")
        logger.info("Updated database statistics")

    conn.close()

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    # Create indexes on live DB
    if DB_FILE.exists():
        create_indexes(DB_FILE, dry_run=args.dry_run)

    # Create indexes on archive DB
    if ARCHIVE_DB_FILE.exists():
        create_indexes(ARCHIVE_DB_FILE, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
```

---

## 8. File Changes Summary

| File | Action | Changes |
|------|--------|---------|
| `shared/database.py` | Modify | Add WAL mode, connection pool, parallel queries |
| `shared/cache.py` | Modify | Add stale-while-revalidate, smart invalidation |
| `shared/metrics.py` | Create | Performance monitoring |
| `tools/create_indexes.py` | Create | Index creation script |
| `api/main.py` | Modify | Add metrics endpoints |
| `api/tools.py` | Modify | Use parallel query executor |

---

## 9. Testing Checklist

### 9.1 Performance Tests
- [ ] Query time < 50ms for common queries
- [ ] P99 < 200ms under load
- [ ] Cache hit rate > 90%
- [ ] No connection pool exhaustion

### 9.2 Correctness Tests
- [ ] UNION queries return same results
- [ ] Aggregation values match original
- [ ] No data corruption after WAL enable

### 9.3 Stress Tests
- [ ] 100 concurrent requests
- [ ] Large result sets (>10k rows)
- [ ] Long-running queries with timeout

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-25 | Initial design |
