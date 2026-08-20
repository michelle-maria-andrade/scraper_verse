# Dino Scraper
For the project pipeline check [.agent/rules/project.md](.agents/rules/projects.md)

TO DOs
### Website

### Scraper
- [x] make the scraper with detailed prompt using Bright data CLI (Collector ID: c_mt1xysv2naavme1zu)
- [x] save the scraped data in a db for future use and comparision (SQLite schema with runs, product_snapshots, and latest_product_snapshots view)
- [] Update the UI and discord agent for discounts and update messages
 
### Differential engine: 
Differential engine should look at previous scrapes and understand if its broken, and use bright data to fix it
- [] 

### Self heal loop
Understand what broke and update the prompt to heal the scraper.
- [] 

### Ui and discord agent updates

## AGENT
-----------------------------------------------------------------------------------------------------------------------------------------
 Reviewing Data Collection
  I have developed and verified the Scraper and Storage components in accordance with projects.md.
  ──────
  ### Summary of What Was Built

  #### 1. Scraper Component

  • AI Scraper Creation: Generated the Bright Data PDP scraper for the target robotics site (indianrobostore.com) using the specified fields
  (product_url, product_name, sku, list_price, discount_price, discount_pct, in_stock, scraped_at).
      • Collector ID: c_mt1xysv2naavme1zu
  • **bdata_client.py**: Python wrapper around the Bright Data CLI (create, run, heal) and REST API (POST /dca/trigger).
  • **models.py**: Pydantic data models with price/currency normalization, stock status parsing, automatic discount percentage calculation, and
  breakage validation (is_valid(), missing_fields()).
  • **runner.py**: Pipeline runner that triggers the collector, normalizes returned records, records run statistics, and persists product snapshots
  to the database.

  #### 2. Storage Component

  • **db.py**: SQLite connection manager with WAL mode and schema initialization:
      • runs table: Tracks run_id, collector_id, status, total_products, valid_products, broken_products, and timestamps.
      • product_snapshots table: Stores product_url, product_name, sku, list_price, discount_price, discount_pct, in_stock, run_id, scraped_at,
      raw_data.
      • latest_product_snapshots view: Fast view retrieving the latest snapshot per product URL.
      • latest_good_product_snapshots view: View retrieving the latest known-good snapshot per product URL (ignoring broken/empty scrapes).
  • **repository.py**: Data access layer for inserting runs, batch saving snapshots, retrieving latest snapshots, and querying product price history.

  #### 3. Configuration & Fixtures

  • **target_urls.json**: Curated list of robotics product URLs.
  • **settings.py** & **.env.example**: Environment settings for collector ID, database path, and API keys.
  • : Mock JSON fixtures for baseline, discount changes, and site breakages for offline testing.
  ──────
  ### Verification

  1. Unit & Integration Tests:
    PYTHONPATH=. .venv/bin/pytest -v -p no:launch_testing

      • Result: 12/12 passed (model normalization, storage CRUD, SQL views, mock scraper runs).
  2. Live Scrape & Storage Verification:
    PYTHONPATH=. .venv/bin/python3 -m src.scraper.runner --url "https://indianrobostore.com/product/male-dupont-electrical-terminal-plug-reed-
  connector-254mm-5-pins"

      • Result: Successfully extracted live data via c_mt1xysv2naavme1zu (₹29.0, was ₹39.0, -26.0%, in stock) and persisted into SQLite scraper.db.
