import argparse
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union

from config.settings import settings
from src.scraper.bdata_client import BrightDataClient, bdata_client
from src.scraper.models import ProductSnapshot, ScrapeRun
from src.storage.repository import ProductSnapshotRepository, repository

logger = logging.getLogger(__name__)


def load_target_urls(urls_path: Optional[Union[str, Path]] = None) -> List[str]:
    """Load target PDP URLs from JSON configuration file."""
    path = Path(urls_path) if urls_path else settings.TARGET_URLS_FILE
    if not path.exists():
        logger.warning(f"Target URLs file not found at {path}, falling back to defaults.")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "urls" in data:
                return data["urls"]
    except Exception as e:
        logger.error(f"Failed to read target URLs from {path}: {e}")
    return []


def get_default_collector_id() -> Optional[str]:
    """Retrieve collector ID from env, settings, or saved create_result.json."""
    if settings.BRIGHTDATA_COLLECTOR_ID:
        return settings.BRIGHTDATA_COLLECTOR_ID
    
    # Check if create_result.json exists in root
    res_path = settings.BASE_DIR / "create_result.json"
    if res_path.exists():
        try:
            with open(res_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                cid = data.get("collector_id")
                if cid:
                    return cid
        except Exception:
            pass
    return None


def execute_scrape_run(
    collector_id: Optional[str] = None,
    urls: Optional[List[str]] = None,
    client: Optional[BrightDataClient] = None,
    repo: Optional[ProductSnapshotRepository] = None,
    sync: bool = False,
    timeout: int = 600,
) -> Tuple[ScrapeRun, List[ProductSnapshot]]:
    """
    Executes a complete scrape run:
    1. Resolves collector ID and target URLs.
    2. Records the start of the run in SQLite storage.
    3. Runs the Bright Data collector.
    4. Normalizes raw outputs into ProductSnapshot instances.
    5. Saves all snapshots and final run status into SQLite storage.
    """
    client = client or bdata_client
    repo = repo or repository

    cid = collector_id or get_default_collector_id()
    if not cid:
        raise ValueError(
            "No collector ID provided. Set BRIGHTDATA_COLLECTOR_ID in .env or provide --collector argument."
        )

    target_urls = urls if urls is not None else load_target_urls()
    if not target_urls:
        raise ValueError("No target URLs provided to scrape.")

    # Generate unique run ID
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{now_str}_{uuid.uuid4().hex[:6]}"
    start_time = datetime.now(timezone.utc).isoformat()

    # Create initial run record in database
    run_record = ScrapeRun(
        run_id=run_id,
        collector_id=cid,
        status="RUNNING",
        total_products=len(target_urls),
        valid_products=0,
        broken_products=0,
        started_at=start_time,
    )
    repo.create_run(run_record)
    logger.info(f"Started scrape run {run_id} with collector {cid} for {len(target_urls)} URLs")

    snapshots: List[ProductSnapshot] = []
    try:
        raw_results = client.run_scraper(
            collector_id=cid,
            urls=target_urls,
            sync=sync,
            timeout=timeout,
        )

        # Normalize raw results into ProductSnapshot models
        for idx, raw in enumerate(raw_results):
            default_url = target_urls[idx] if idx < len(target_urls) else ""
            snapshot = ProductSnapshot.from_raw_dict(
                raw=raw,
                run_id=run_id,
                default_url=default_url,
            )
            snapshots.append(snapshot)

        # In case the scraper returned fewer items than target_urls, fill missing as broken
        scraped_urls = {s.product_url for s in snapshots}
        for u in target_urls:
            if u not in scraped_urls:
                snapshots.append(
                    ProductSnapshot(
                        run_id=run_id,
                        product_url=u,
                        product_name=None,
                        list_price=None,
                        discount_price=None,
                        discount_pct=None,
                        in_stock=False,
                        scraped_at=datetime.now(timezone.utc).isoformat(),
                        raw_data={"error": "URL missing in scraper response"},
                    )
                )

        # Compute validity stats
        valid_count = sum(1 for s in snapshots if s.is_valid())
        broken_count = len(snapshots) - valid_count

        # Save snapshots in SQLite
        repo.save_product_snapshots(snapshots)

        # Update run status
        run_record.status = "SUCCESS" if broken_count == 0 else ("PARTIAL" if valid_count > 0 else "FAILED")
        run_record.total_products = len(snapshots)
        run_record.valid_products = valid_count
        run_record.broken_products = broken_count
        run_record.completed_at = datetime.now(timezone.utc).isoformat()
        repo.update_run(run_record)

        logger.info(
            f"Completed run {run_id}: total={len(snapshots)}, valid={valid_count}, broken={broken_count}"
        )
        return run_record, snapshots

    except Exception as e:
        logger.error(f"Scrape run {run_id} failed: {e}")
        run_record.status = "FAILED"
        run_record.completed_at = datetime.now(timezone.utc).isoformat()
        run_record.error_message = str(e)
        repo.update_run(run_record)
        raise


def main():
    """CLI execution entrypoint for running the scraper."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Run Bright Data PDP discount scraper and store snapshots.")
    parser.add_argument("--collector", "-c", type=str, help="Collector ID (e.g. c_xxx)")
    parser.add_argument("--url", "-u", type=str, action="append", help="Target URL(s) to scrape")
    parser.add_argument("--urls-file", "-f", type=str, help="Path to JSON file containing target URLs")
    parser.add_argument("--sync", action="store_true", help="Run in synchronous mode (single URL)")
    parser.add_argument("--json", action="store_true", help="Output summary as JSON")

    args = parser.parse_args()

    urls = args.url
    if not urls and args.urls_file:
        urls = load_target_urls(args.urls_file)

    run_record, snapshots = execute_scrape_run(
        collector_id=args.collector,
        urls=urls,
        sync=args.sync,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "run": run_record.model_dump(),
                    "snapshots": [s.model_dump() for s in snapshots],
                },
                indent=2,
            )
        )
    else:
        print(f"\n================ Scrape Run Summary ================")
        print(f"Run ID:          {run_record.run_id}")
        print(f"Collector ID:    {run_record.collector_id}")
        print(f"Status:          {run_record.status}")
        print(f"Total Products:  {run_record.total_products}")
        print(f"Valid Products:  {run_record.valid_products}")
        print(f"Broken Products: {run_record.broken_products}")
        print(f"Started:         {run_record.started_at}")
        print(f"Completed:       {run_record.completed_at}")
        print(f"===================================================\n")
        for s in snapshots:
            valid_mark = "✓" if s.is_valid() else "✗ (BROKEN)"
            price_info = f"₹{s.discount_price}" if s.discount_price else "No price"
            if s.list_price and s.list_price > (s.discount_price or 0):
                price_info += f" (was ₹{s.list_price}, -{s.discount_pct}%)"
            print(f"[{valid_mark}] {s.product_name or 'NO_NAME'}")
            print(f"     URL:   {s.product_url}")
            print(f"     SKU:   {s.sku or 'N/A'}")
            print(f"     Price: {price_info}")
            print(f"     Stock: {'In Stock' if s.in_stock else 'Out of Stock'}")
            print()


if __name__ == "__main__":
    main()
