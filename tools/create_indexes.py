#!/usr/bin/env python3
"""
Database Index Creation Script

Creates optimized indexes for production_records table.
Run this script once after database is created or when performance degrades.

Usage:
    python tools/create_indexes.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import ARCHIVE_DB_FILE, DB_FILE
from shared.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


# ==========================================================
# Index Definitions
# ==========================================================
# Format: (index_name, table, columns, description)
INDEXES = [
    (
        "idx_production_date_item",
        "production_records",
        "(production_date, item_code)",
        "Composite index for date range + item queries"
    ),
    (
        "idx_lot_number",
        "production_records",
        "(lot_number)",
        "Index for lot number prefix searches"
    ),
    (
        "idx_agg_covering",
        "production_records",
        "(item_code, production_date, good_quantity)",
        "Covering index for common aggregations"
    ),
    (
        "idx_date_qty",
        "production_records",
        "(production_date, good_quantity)",
        "Index for date-ordered quantity queries"
    ),
]


def get_existing_indexes(conn: sqlite3.Connection) -> set[str]:
    """Get set of existing index names."""
    result = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type = 'index' AND sql IS NOT NULL
    """).fetchall()
    return {row[0] for row in result}


def get_table_stats(conn: sqlite3.Connection, table: str = "production_records") -> dict:
    """Get table statistics."""
    stats = {}

    # Row count
    result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    stats["row_count"] = result[0] if result else 0

    # Table size (approximate) - try dbstat first, then file size
    try:
        result = conn.execute(f"""
            SELECT SUM(pgsize) FROM dbstat
            WHERE name = '{table}'
        """).fetchone()
        stats["table_size_mb"] = round((result[0] or 0) / (1024 * 1024), 2)
    except sqlite3.OperationalError:
        # dbstat not available, skip size calculation
        stats["table_size_mb"] = "N/A"

    return stats


def create_indexes(db_path: Path, dry_run: bool = False, force: bool = False) -> None:
    """
    Create indexes on database.

    Args:
        db_path: Path to SQLite database
        dry_run: If True, only print what would be done
        force: If True, recreate existing indexes
    """
    logger.info(f"Processing database: {db_path}")

    if not db_path.exists():
        logger.warning(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    # Enable dbstat for size calculation
    try:
        conn.execute("PRAGMA stats = ON")
    except sqlite3.Error:
        pass  # Not all SQLite versions support this

    # Get stats
    stats = get_table_stats(conn)
    logger.info(f"Table stats: {stats['row_count']:,} rows")

    # Get existing indexes
    existing = get_existing_indexes(conn)
    logger.info(f"Existing indexes: {existing}")

    created = 0
    skipped = 0

    for index_name, table, columns, description in INDEXES:
        if index_name in existing and not force:
            logger.info(f"[SKIP] {index_name} already exists - {description}")
            skipped += 1
            continue

        sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}{columns}"

        if dry_run:
            logger.info(f"[DRY RUN] {sql}")
            logger.info(f"         -> {description}")
        else:
            start = time.time()
            try:
                conn.execute(sql)
                conn.commit()
                elapsed = time.time() - start
                logger.info(f"[OK] {index_name} created in {elapsed:.2f}s - {description}")
                created += 1
            except sqlite3.Error as e:
                logger.error(f"[FAIL] {index_name}: {e}")

    # Update statistics
    if not dry_run and created > 0:
        logger.info("Running ANALYZE to update statistics...")
        conn.execute("ANALYZE")
        conn.commit()

    conn.close()

    logger.info(f"Done: {created} created, {skipped} skipped")


def verify_indexes(db_path: Path) -> None:
    """Verify index usage with sample queries."""
    logger.info(f"\nVerifying indexes on {db_path}")

    conn = sqlite3.connect(db_path)

    test_queries = [
        ("Date range query", """
            SELECT * FROM production_records
            WHERE production_date >= '2026-01-01' AND production_date < '2026-02-01'
            LIMIT 10
        """),
        ("Item aggregation", """
            SELECT item_code, SUM(good_quantity)
            FROM production_records
            WHERE production_date >= '2026-01-01'
            GROUP BY item_code
        """),
        ("Lot number search", """
            SELECT * FROM production_records
            WHERE lot_number LIKE '2%'
            LIMIT 10
        """),
    ]

    for name, query in test_queries:
        plan = conn.execute(f"EXPLAIN QUERY PLAN {query}").fetchall()
        uses_index = any("INDEX" in str(row) for row in plan)
        status = "USING INDEX" if uses_index else "FULL SCAN"
        logger.info(f"{name}: {status}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Create optimized indexes for Production Data Hub"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recreate existing indexes"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify index usage after creation"
    )
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Production Data Hub - Index Creation")
    logger.info("=" * 50)

    # Process live DB
    if DB_FILE.exists():
        create_indexes(DB_FILE, dry_run=args.dry_run, force=args.force)
        if args.verify and not args.dry_run:
            verify_indexes(DB_FILE)
    else:
        logger.warning(f"Live DB not found: {DB_FILE}")

    # Process archive DB
    if ARCHIVE_DB_FILE.exists():
        logger.info("")
        create_indexes(ARCHIVE_DB_FILE, dry_run=args.dry_run, force=args.force)
        if args.verify and not args.dry_run:
            verify_indexes(ARCHIVE_DB_FILE)
    else:
        logger.info(f"Archive DB not found (optional): {ARCHIVE_DB_FILE}")

    logger.info("=" * 50)
    logger.info("Index creation complete!")


if __name__ == "__main__":
    main()
