import sqlite3
from pathlib import Path

# ==========================================================
# Configuration
# ==========================================================
BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "database"
LIVE_DB = DB_DIR / "production_analysis.db"
ARCHIVE_DB = DB_DIR / "archive_2025.db"

# ==========================================================
# Index SQL Definitions
# ==========================================================
INDEX_SQLS = [
    "CREATE INDEX IF NOT EXISTS idx_production_date ON production_records(production_date)",
    "CREATE INDEX IF NOT EXISTS idx_item_code ON production_records(item_code)"
]

def create_index(db_path: Path, label: str):
    if not db_path.exists():
        print(f"[{label}] Skip: File not found ({db_path})")
        return

    print(f"[{label}] Creating indexes on {db_path}...")
    try:
        with sqlite3.connect(str(db_path)) as conn:
            for sql in INDEX_SQLS:
                print(f"  - Executing: {sql}")
                conn.execute(sql)
            print(f"[{label}] Done.")
    except sqlite3.Error as e:
        print(f"[{label}] Error: {e}")

if __name__ == "__main__":
    print(">>> Starting Index Creation Task...")
    create_index(LIVE_DB, "LIVE DB")
    create_index(ARCHIVE_DB, "ARCHIVE DB (2025)")
    print(">>> All tasks completed.")
