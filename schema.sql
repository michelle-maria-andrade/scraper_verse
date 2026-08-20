-- Table for information about the target site, the Bright Data collector ID, and the last known status.
CREATE TABLE monitors (
  id            SERIAL PRIMARY KEY,
  name          TEXT NOT NULL,              
  collector_id  TEXT NOT NULL,              
  target_url    TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'healthy', 
  schedule      TEXT,                        
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table for each run of the scraper. Powers the Runs tab and the Run Details page.
CREATE TABLE runs (
  id            SERIAL PRIMARY KEY,
  monitor_id    INTEGER NOT NULL REFERENCES monitors(id),
  snapshot_id   TEXT,                        
  status        TEXT NOT NULL DEFAULT 'pending', 
  data          JSONB,                       
  error_message TEXT,                       
  duration_ms   INTEGER,
  ran_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table for each break, heal, approval, or diff. Powers the Breaks tab and the Run Details page.
CREATE TABLE events (
  id            SERIAL PRIMARY KEY,
  monitor_id    INTEGER NOT NULL REFERENCES monitors(id),
  run_id        INTEGER REFERENCES runs(id), 
  type          TEXT NOT NULL,               
  message       TEXT NOT NULL,               
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Table for the latest known state of each product. Used to power the Products tab and the Discord message.
CREATE TABLE products (
  id              SERIAL PRIMARY KEY,
  monitor_id      INTEGER NOT NULL REFERENCES monitors(id),
  product_url     TEXT NOT NULL,
  product_name    TEXT,
  sku             TEXT,
  list_price      NUMERIC,
  discount_price  NUMERIC,
  discount_pct    NUMERIC,
  in_stock        BOOLEAN,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (monitor_id, product_url)
);

-- Table for each product snapshot. Powers the Run Details page and the Product Details page.
CREATE TABLE product_snapshots (
  id              SERIAL PRIMARY KEY,
  monitor_id      INTEGER NOT NULL REFERENCES monitors(id),
  run_id          INTEGER NOT NULL REFERENCES runs(id),
  product_url     TEXT NOT NULL,
  product_name    TEXT,
  sku             TEXT,
  list_price      NUMERIC,
  discount_price  NUMERIC,
  discount_pct    NUMERIC,
  in_stock        BOOLEAN,
  scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per GitHub Actions run. Powers the green/red check wall.
CREATE TABLE ci_checks (
  id            SERIAL PRIMARY KEY,
  monitor_id    INTEGER NOT NULL REFERENCES monitors(id),
  status        TEXT NOT NULL,              
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);