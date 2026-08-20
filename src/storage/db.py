import sqlite3
from pathlib import Path
from typing import Optional, Union
from config.settings import settings


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    collector_id TEXT,
    status TEXT NOT NULL,
    total_products INTEGER DEFAULT 0,
    valid_products INTEGER DEFAULT 0,
    broken_products INTEGER DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS product_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    product_url TEXT NOT NULL,
    product_name TEXT,
    sku TEXT,
    list_price REAL,
    discount_price REAL,
    discount_pct REAL,
    in_stock INTEGER NOT NULL DEFAULT 1,
    scraped_at TEXT NOT NULL,
    raw_data TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (run_id) REFERENCES runs (run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_product_snapshots_url ON product_snapshots(product_url);
CREATE INDEX IF NOT EXISTS idx_product_snapshots_run_id ON product_snapshots(run_id);
CREATE INDEX IF NOT EXISTS idx_product_snapshots_scraped_at ON product_snapshots(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);

-- View for the latest snapshot per product URL (regardless of validity)
CREATE VIEW IF NOT EXISTS latest_product_snapshots AS
SELECT ps.*
FROM product_snapshots ps
INNER JOIN (
    SELECT product_url, MAX(id) AS max_id
    FROM product_snapshots
    GROUP BY product_url
) latest ON ps.product_url = latest.product_url AND ps.id = latest.max_id;

-- View for the most recent known-good / valid snapshot per product URL
CREATE VIEW IF NOT EXISTS latest_good_product_snapshots AS
SELECT ps.*
FROM product_snapshots ps
INNER JOIN (
    SELECT product_url, MAX(id) AS max_id
    FROM product_snapshots
    WHERE product_name IS NOT NULL 
      AND TRIM(product_name) != '' 
      AND (list_price IS NOT NULL OR discount_price IS NOT NULL)
    GROUP BY product_url
) latest ON ps.product_url = latest.product_url AND ps.id = latest.max_id;
"""


class DatabaseManager:
    """
    Manages SQLite database connection and schema lifecycle.
    """
    def __init__(self, db_path: Union[str, Path, None] = None):
        self.db_path = Path(db_path) if db_path and db_path != ":memory:" else (":memory:" if db_path == ":memory:" else settings.DB_PATH)
        self._memory_conn: Optional[sqlite3.Connection] = None
        self._ensure_db_dir()
        self.init_db()

    def _ensure_db_dir(self):
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:")
                self._memory_conn.row_factory = sqlite3.Row
                self._memory_conn.execute("PRAGMA foreign_keys = ON;")
            return self._memory_conn

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self):
        """Creates tables, indices, and views if they do not exist."""
        conn = self.get_connection()
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        if self.db_path != ":memory:":
            conn.close()


# Default singleton instance
db_manager = DatabaseManager()
