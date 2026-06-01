# tools/db_watcher.py
"""
DB Watcher - Background Database Monitoring Thread

Watches Live and Archive DB files for changes (mtime/size),
waits for stabilization, and auto-heals indexes when needed.

Extracted from manager.py for separation of concerns.
"""

import os
import sqlite3
import threading
import time
from pathlib import Path
from queue import Queue

from shared import ARCHIVE_DB_FILE, DB_FILE
from shared.db_maintenance import (
    check_and_heal_indexes,
    get_file_state,
    wait_for_stabilization,
)


class DBWatcher(threading.Thread):
    def __init__(self, log_queue: Queue, interval: int = 3600):
        super().__init__(daemon=True)
        self.log_queue = log_queue
        self.interval = interval  # Default 1 hour
        self.running = False
        # Track both Live and Archive DBs
        self.db_states: dict[str, tuple[float, int]] = {}

        for db_file in [DB_FILE, ARCHIVE_DB_FILE]:
            if db_file.exists():
                self.db_states[str(db_file)] = (
                    os.path.getmtime(db_file),
                    os.path.getsize(db_file),
                )

    def run(self):
        self.running = True
        self.log_queue.put(("SUCCESS", "✅ DB Watcher Started (Interval: 1h)"))

        while self.running:
            try:
                for _ in range(self.interval):
                    if not self.running:
                        break
                    time.sleep(1)

                if not self.running:
                    break
                self._check_and_heal()

            except sqlite3.Error as e:
                self.log_queue.put(("ERROR", f"Watcher Error: {e}"))
                time.sleep(60)

    def stop(self):
        self.running = False
        self.log_queue.put(("INFO", "🛑 DB Watcher Stopped"))

    def _check_and_heal(self):
        """Check both Live and Archive DBs for changes and heal indexes."""
        for db_path_str, (last_mtime, last_size) in list(self.db_states.items()):
            db_file = Path(db_path_str)
            if not db_file.exists():
                continue

            current_mtime = os.path.getmtime(db_file)
            current_size = os.path.getsize(db_file)

            if current_mtime != last_mtime or current_size != last_size:
                db_name = db_file.name
                self.log_queue.put(("WARN", f"🔄 DB Change Detected ({db_name})! Waiting for stabilization..."))

                if wait_for_stabilization(db_file):
                    self.log_queue.put(("INFO", f"✅ {db_name} Stabilized. Checking indexes..."))
                    result = check_and_heal_indexes(db_file)
                    if result["healed"]:
                        self.log_queue.put(("SUCCESS", f"♻️ [{db_name}] Auto-Healed Indexes: {', '.join(result['healed'])}"))
                    elif result["error"]:
                        self.log_queue.put(("ERROR", f"❌ [{db_name}] Index Heal Failed: {result['error']}"))
                    else:
                        self.log_queue.put(("INFO", f"👍 [{db_name}] Indexes are healthy."))
                    self.db_states[db_path_str] = get_file_state(db_file)
                else:
                    self.log_queue.put(("WARN", f"⚠️ {db_name} unstable. Skip this cycle."))

    def manual_trigger(self):
        threading.Thread(target=self._check_and_heal, daemon=True).start()
