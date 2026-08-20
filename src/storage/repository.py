import json
import sqlite3
from typing import List, Optional
from src.scraper.models import ProductSnapshot, ScrapeRun
from src.storage.db import DatabaseManager, db_manager


class ProductSnapshotRepository:
    """
    Data access layer for ScrapeRuns and ProductSnapshots in SQLite.
    """
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or db_manager

    def _row_to_snapshot(self, row: sqlite3.Row) -> ProductSnapshot:
        raw_data = None
        if row["raw_data"]:
            try:
                raw_data = json.loads(row["raw_data"])
            except Exception:
                raw_data = None

        return ProductSnapshot(
            id=row["id"],
            run_id=row["run_id"],
            product_url=row["product_url"],
            product_name=row["product_name"],
            sku=row["sku"],
            list_price=row["list_price"],
            discount_price=row["discount_price"],
            discount_pct=row["discount_pct"],
            in_stock=bool(row["in_stock"]),
            scraped_at=row["scraped_at"],
            raw_data=raw_data,
        )

    def _row_to_run(self, row: sqlite3.Row) -> ScrapeRun:
        return ScrapeRun(
            run_id=row["run_id"],
            collector_id=row["collector_id"],
            status=row["status"],
            total_products=row["total_products"],
            valid_products=row["valid_products"],
            broken_products=row["broken_products"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
        )

    def create_run(self, run: ScrapeRun) -> ScrapeRun:
        """Insert a new scrape run record."""
        sql = """
        INSERT INTO runs (
            run_id, collector_id, status, total_products, valid_products, 
            broken_products, started_at, completed_at, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.db.get_connection() as conn:
            conn.execute(sql, (
                run.run_id,
                run.collector_id,
                run.status,
                run.total_products,
                run.valid_products,
                run.broken_products,
                run.started_at,
                run.completed_at,
                run.error_message,
            ))
            conn.commit()
        return run

    def update_run(self, run: ScrapeRun):
        """Update an existing scrape run record."""
        sql = """
        UPDATE runs SET
            collector_id = ?,
            status = ?,
            total_products = ?,
            valid_products = ?,
            broken_products = ?,
            completed_at = ?,
            error_message = ?
        WHERE run_id = ?
        """
        with self.db.get_connection() as conn:
            conn.execute(sql, (
                run.collector_id,
                run.status,
                run.total_products,
                run.valid_products,
                run.broken_products,
                run.completed_at,
                run.error_message,
                run.run_id,
            ))
            conn.commit()

    def get_run(self, run_id: str) -> Optional[ScrapeRun]:
        """Fetch a scrape run by run_id."""
        sql = "SELECT * FROM runs WHERE run_id = ?"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (run_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_run(row)
        return None

    def list_runs(self, limit: int = 20) -> List[ScrapeRun]:
        """List past runs sorted descending by started_at."""
        sql = "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (limit,))
            return [self._row_to_run(row) for row in cursor.fetchall()]

    def get_latest_run(self) -> Optional[ScrapeRun]:
        """Fetch the most recent run."""
        runs = self.list_runs(limit=1)
        return runs[0] if runs else None

    def save_product_snapshot(self, snapshot: ProductSnapshot) -> int:
        """Insert a single product snapshot."""
        sql = """
        INSERT INTO product_snapshots (
            run_id, product_url, product_name, sku, list_price, 
            discount_price, discount_pct, in_stock, scraped_at, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        raw_json = json.dumps(snapshot.raw_data) if snapshot.raw_data else None
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (
                snapshot.run_id,
                snapshot.product_url,
                snapshot.product_name,
                snapshot.sku,
                snapshot.list_price,
                snapshot.discount_price,
                snapshot.discount_pct,
                1 if snapshot.in_stock else 0,
                snapshot.scraped_at,
                raw_json,
            ))
            conn.commit()
            return cursor.lastrowid

    def save_product_snapshots(self, snapshots: List[ProductSnapshot]) -> int:
        """Batch insert product snapshots inside a transaction."""
        if not snapshots:
            return 0
        sql = """
        INSERT INTO product_snapshots (
            run_id, product_url, product_name, sku, list_price, 
            discount_price, discount_pct, in_stock, scraped_at, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                s.run_id,
                s.product_url,
                s.product_name,
                s.sku,
                s.list_price,
                s.discount_price,
                s.discount_pct,
                1 if s.in_stock else 0,
                s.scraped_at,
                json.dumps(s.raw_data) if s.raw_data else None,
            )
            for s in snapshots
        ]
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(sql, rows)
            conn.commit()
            return cursor.rowcount

    def get_latest_snapshot(self, product_url: str, only_valid: bool = False) -> Optional[ProductSnapshot]:
        """Fetch the most recent snapshot for a specific product URL."""
        table_or_view = "latest_good_product_snapshots" if only_valid else "latest_product_snapshots"
        sql = f"SELECT * FROM {table_or_view} WHERE product_url = ?"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (product_url,))
            row = cursor.fetchone()
            if row:
                return self._row_to_snapshot(row)
        return None

    def get_all_latest_snapshots(self, only_valid: bool = False) -> List[ProductSnapshot]:
        """Fetch the most recent snapshot for every tracked product URL."""
        table_or_view = "latest_good_product_snapshots" if only_valid else "latest_product_snapshots"
        sql = f"SELECT * FROM {table_or_view} ORDER BY product_name ASC"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            return [self._row_to_snapshot(row) for row in cursor.fetchall()]

    def get_snapshots_by_run(self, run_id: str) -> List[ProductSnapshot]:
        """Fetch all product snapshots produced in a specific run."""
        sql = "SELECT * FROM product_snapshots WHERE run_id = ? ORDER BY id ASC"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (run_id,))
            return [self._row_to_snapshot(row) for row in cursor.fetchall()]

    def get_product_history(self, product_url: str, limit: int = 50) -> List[ProductSnapshot]:
        """Fetch the historical timeline of snapshots for a single product."""
        sql = "SELECT * FROM product_snapshots WHERE product_url = ? ORDER BY id DESC LIMIT ?"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (product_url, limit))
            return [self._row_to_snapshot(row) for row in cursor.fetchall()]

    def get_product_count(self) -> int:
        """Count distinct products tracked."""
        sql = "SELECT COUNT(DISTINCT product_url) as cnt FROM product_snapshots"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            row = cursor.fetchone()
            return row["cnt"] if row else 0


repository = ProductSnapshotRepository()
