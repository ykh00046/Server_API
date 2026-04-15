# Database Performance Optimization Plan

> **Feature**: DB Performance Optimization
> **Status**: Planning
> **Priority**: High
> **Created**: 2026-02-25

---

## 1. Overview

### 1.1 Goals
- Reduce query response time by 50%
- Optimize database file size and storage
- Implement efficient caching strategies
- Improve concurrent access handling

### 1.2 Scope
- SQLite database optimization
- Query performance tuning
- Connection pooling improvements
- Caching layer enhancement

---

## 2. Current State Analysis

### 2.1 Database Statistics
| Metric | Current Value | Notes |
|--------|---------------|-------|
| Live DB Size | ~XX MB | `production_analysis.db` |
| Archive DB Size | ~XX MB | `archive_2025.db` |
| Total Records | ~XX,XXX | Combined live + archive |
| Avg Query Time | ~50-200ms | Depending on complexity |

### 2.2 Current Implementation
| Component | Location | Issues |
|-----------|----------|--------|
| DB Router | `shared/database.py` | Thread-local caching works well |
| Query Builder | `shared/database.py` | Could use more index hints |
| API Cache | `shared/cache.py` | TTLCache works, could be smarter |
| Connection Pool | Thread-local | No explicit pool size limit |

### 2.3 Identified Bottlenecks
1. **LIKE Queries** - Full table scans on text search
2. **Date Range Queries** - No composite index on (date, item_code)
3. **Archive UNION** - Large UNION ALL queries can be slow
4. **Cache Invalidation** - mtime-based, could use smarter invalidation

---

## 3. Proposed Optimizations

### 3.1 Phase 1: Index Optimization
| ID | Task | Priority | Impact |
|----|------|----------|--------|
| DB-01 | Add composite index on (production_date, item_code) | High | High |
| DB-02 | Add index on lot_number prefix | Medium | Medium |
| DB-03 | Analyze query plans with EXPLAIN QUERY PLAN | High | - |
| DB-04 | Add covering indexes for common queries | Medium | High |
| DB-05 | Implement index usage monitoring | Low | Medium |

### 3.2 Phase 2: Query Optimization
| ID | Task | Priority | Impact |
|----|------|----------|--------|
| QO-01 | Optimize UNION ALL with parallel execution | Medium | High |
| QO-02 | Add query result streaming for large datasets | Medium | Medium |
| QO-03 | Implement query timeout with progress | Low | Low |
| QO-04 | Add prepared statement caching | Low | Medium |
| QO-05 | Optimize aggregation queries | High | High |

### 3.3 Phase 3: Caching Enhancement
| ID | Task | Priority | Impact |
|----|------|----------|--------|
| CE-01 | Implement smarter cache invalidation | High | High |
| CE-02 | Add query result pre-computation | Medium | Medium |
| CE-03 | Implement cache warming on startup | Low | Low |
| CE-04 | Add cache hit/miss metrics | Medium | Low |
| CE-05 | Implement stale-while-revalidate pattern | Medium | High |

### 3.4 Phase 4: Storage Optimization
| ID | Task | Priority | Impact |
|----|------|----------|--------|
| SO-01 | Run VACUUM to reclaim space | High | Medium |
| SO-02 | Enable WAL mode for better concurrency | High | High |
| SO-03 | Implement automatic DB integrity check | Medium | Low |
| SO-04 | Add DB size monitoring and alerts | Medium | Low |
| SO-05 | Implement incremental backup strategy | Low | Medium |

---

## 4. Technical Requirements

### 4.1 SQLite Optimizations
```sql
-- Enable WAL mode
PRAGMA journal_mode=WAL;

-- Set cache size (negative = KB)
PRAGMA cache_size=-64000;  -- 64MB

-- Enable memory-mapped I/O
PRAGMA mmap_size=268435456;  -- 256MB

-- Set busy timeout
PRAGMA busy_timeout=5000;
```

### 4.2 Recommended Indexes
```sql
-- Composite index for date-range + item queries
CREATE INDEX IF NOT EXISTS idx_production_date_item
ON production_records(production_date, item_code);

-- Index for lot number searches
CREATE INDEX IF NOT EXISTS idx_lot_number
ON production_records(lot_number);

-- Covering index for common aggregations
CREATE INDEX IF NOT EXISTS idx_agg_covering
ON production_records(item_code, production_date, good_quantity);
```

### 4.3 Performance Targets
| Metric | Current | Target |
|--------|---------|--------|
| Avg Query Time | 50-200ms | <50ms |
| P99 Query Time | ~500ms | <200ms |
| Cache Hit Rate | ~70% | >90% |
| DB File Size Growth | ~10MB/day | ~5MB/day |

---

## 5. Implementation Order

```
Week 1: Phase 1 & 2 (Index + Query)
  ├── DB-03: EXPLAIN analysis
  ├── DB-01: Composite index
  ├── QO-05: Aggregation optimization
  └── SO-02: Enable WAL mode

Week 2: Phase 3 (Caching)
  ├── CE-01: Smart invalidation
  ├── CE-05: Stale-while-revalidate
  └── CE-04: Cache metrics

Week 3: Phase 4 (Storage)
  ├── SO-01: VACUUM
  ├── SO-03: Integrity check
  └── SO-04: Size monitoring
```

---

## 6. Success Criteria

- [ ] Average query time < 50ms
- [ ] P99 query time < 200ms
- [ ] Cache hit rate > 90%
- [ ] No database corruption after stress test
- [ ] WAL mode enabled and stable

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Index increases DB size | Low | Monitor size, drop unused indexes |
| WAL mode compatibility | Medium | Test thoroughly, have rollback plan |
| Cache invalidation bugs | High | Add comprehensive logging |
| Migration failure | High | Backup before any schema changes |

---

## 8. Dependencies

- UI/UX Enhancement (parallel track)
- Backup strategy before schema changes

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-25 | Initial plan |
