# Project: Self-Healing Robotics Discount Scraper → Discord Alerts

## Objective
Build a scraper for a robotics sales site that periodically checks product pages
for discounts, detects when a discount appears/changes, and posts an update to
Discord. If the site's HTML structure changes and the scraper starts returning
missing/null fields, detect that automatically, trigger a self-heal via the
Bright Data scraper agent, verify the fix, and resume collection — with zero
manual code changes to the downstream pipeline.

No UI/dashboard is in scope. This is a headless pipeline: scraper → storage →
diff → Discord.

## Target site
`<TARGET_SITE_URL>` — a robotics sales site with individual product detail
pages (PDPs). Fill this in before starting. Confirm it does NOT already have
a pre-built Bright Data scraper (check the marketplace first — if one exists,
pick a different target or a narrower niche, e.g. a specific category or
regional distributor).

## Architecture

```
┌─────────────┐   POST /dca/trigger   ┌──────────────────┐
│  Scheduler   │ ───────────────────► │ Bright Data       │
│ (cron/GH     │                      │ Collector (c_xxx) │
│  Actions)    │ ◄─────────────────── │ PDP scraper       │
└─────────────┘   JSON results        └──────────────────┘
                                              │
                                              ▼
                                    ┌───────────────────┐
                                    │ Diff engine        │
                                    │ (compare vs last   │
                                    │  snapshot in DB)   │
                                    └───────────────────┘
                                       │              │
                             discount changed   fields missing
                                       │              │
                                       ▼              ▼
                              ┌──────────────┐  ┌──────────────────┐
                              │ Discord      │  │ bdata scraper     │
                              │ webhook post │  │ heal + re-verify  │
                              └──────────────┘  └──────────────────┘
```
## Schema

- monitors

  1. id — a unique number for the monitor.
  2. name — human-readable label for display UI display.
  3. collector_id — the Bright Data Collector ID to trigger scrapes via the API 
  4. target_url — the URL being scraped.
  5. status — current state: 'healthy', 'healing', or 'broken'. 
  6. schedule — human-readable text like "hourly" for UI display thats taken from cron timing on Github Actions.
  7. created_at — timestamp of when the monitor was first added

- runs

  1. id — unique number per run.
  2. monitor_id — which monitor this run belongs to. (FK)
  3. snapshot_id — for polling the data collection.
  4. status — 'pending' (still waiting on Bright Data), 'success', or 'failed'. Defaults to 'pending' because when a run starts, it hasn't finished yet.
  5. data — the actual scraped JSON result 
  6. error_message — only filled in if status = 'failed'. Explains what went wrong.
  7. duration_ms — how long the run took, in milliseconds for UI.
  8. ran_at — timestamp of when the run happened.

- events

  1. id — unique number per event.
  2. monitor_id — logs monitor id for event.
  3. run_id — optional link to the specific run that revealed this event (e.g. "run #3 is the one that showed the break"). Can be NULL if there's no specific run tied to it.
  4. type — one of 'break', 'heal', 'approve', or 'diff' for the UI.
  5. message — the human-readable description, e.g. "discount_price returning null on ~80% of rows".
  6. created_at — timestamp of when the event happened. 

- products

  1. id — unique number per product.
  2. monitor_id — which monitor this product belongs to. (FK)
  3. product_url — the product's page URL. Combined with monitor_id, uniquely identifies one product — never duplicated, always overwritten.
  4. product_name — display name of the product.
  5. sku — product SKU/code, if the site has one.
  6. list_price — the original (non-discounted) price.
  7. discount_price — the current discounted price, if any.
  8. discount_pct — the discount percentage.
  9. in_stock — whether the product is currently in stock.
  10. updated_at — timestamp of the last time this row was refreshed with new scraped values. 

- product_snapshots

  1. id — unique number per snapshot.
  2. monitor_id — which monitor this snapshot belongs to. (FK)
  3. run_id — which run produced this snapshot. (FK, required — every snapshot comes from exactly one run)
  4. product_url — the product's page URL.
  5. product_name, sku, list_price, discount_price, discount_pct, in_stock — but this is a frozen copy at the time of a specific run, never overwritten.
  6. scraped_at — timestamp of when this snapshot was taken. 
  
- ci_checks

  1. id — unique number per check.
  2. monitor_id — which monitor this CI run was checking.
  3. status — 'pass' or 'fail'. This is literally what colors each square in the green/red check wall.
  4. created_at — timestamp, used to order the checks left-to-right in the wall.

## Components

### 1. Scraper (Bright Data, PDP type)
- Create with `bdata scraper create` against 5-10 sample product URLs from
  the target site.
- Required fields to extract per product: `product_url`, `product_name`,
  `sku` (if available), `list_price`, `discount_price`, `discount_pct`,
  `in_stock`, `scraped_at`.
- Save the resulting Collector ID (`c_*`) — this is the stable interface the
  rest of the pipeline talks to. Nothing downstream should ever need to
  change when the scraper internals change.

### 2. Storage
- Simplest viable option: SQLite file (or a `snapshots.json` if you want
  zero-dependency). One row per product per run, plus a `latest` view/table
  for the most recent known-good value per product.
- Schema: `product_url, product_name, list_price, discount_price,
  discount_pct, in_stock, run_id, scraped_at`.

### 3. Diff / change-detection logic
- Compare each run's results against the last stored "good" snapshot per
  product.
- **Discount change** (price dropped, discount_pct increased, or a product
  newly has a discount) → queue a Discord notification.
- **Breakage signal**: if more than some threshold (e.g. >30%) of scraped
  products come back with `null`/missing `product_name` or `list_price` in
  a single run, treat this as a site-structure change, not a real data
  change. Do NOT post discount alerts based on broken data. Flag for heal
  instead.

### 4. Self-heal loop
- On a breakage signal:
  1. Log what broke (which fields, what % of rows, a couple of example URLs).
  2. Run `bdata scraper heal` against the Collector ID with a description of
     the failure (e.g. "discount_price and product_name returning null on
     ~80% of products, site likely changed page layout").
  3. Re-run the scraper against the same sample URLs used for verification.
  4. Confirm the previously-missing fields are now populated before
     resuming the normal scheduled run.
  5. Post a Discord message noting the scraper self-healed (this is your
     best demo moment — don't skip it).
- Same Collector ID throughout. No changes to storage schema, diff logic,
  or Discord code when a heal happens.

### 5. Discord notifications
- Use a Discord webhook (simplest, no bot hosting required) for posting
  discount alerts and heal events.
- Message format for a discount:
  `🔻 [Product Name] now $X (was $Y, -Z%) — <product_url>`
- Message format for a heal event:
  `🛠️ Scraper self-healed: [what broke] → fixed and verified. Resuming normal runs.`

### 6. Scheduler
- GitHub Actions on a cron schedule (e.g. every hour or every 6 hours),
  calling `POST /dca/trigger` on the Collector ID, then running the diff +
  heal-check script.
- Keep the Bright Data API token and Discord webhook URL as GitHub Actions
  secrets — never commit them or print them in logs.

## Build order (for the coding agent)
1. Confirm target site + pull 5-10 sample product URLs.
2. `bdata scraper create` (PDP) → verify clean JSON via `bdata scraper run`
   on the samples.
3. Build storage layer + write the diff logic against stored fixtures
   (mock a "before" and "after" JSON to test discount detection without
   hitting the live site repeatedly).
4. Wire up Discord webhook posting for discount changes.
5. Add breakage detection (missing-field threshold) + wire up
   `bdata scraper heal` invocation and re-verification.
6. Wrap the whole flow in a script triggerable via `POST /dca/trigger`.
7. Add GitHub Actions workflow with cron schedule + secrets.
8. Test end-to-end: force a fake breakage (e.g. point at a modified/staging
   HTML fixture, or temporarily corrupt a field mapping) and confirm heal
   → re-verify → resume works without touching downstream code.

## Environment / secrets
- `BRIGHTDATA_API_TOKEN`
- `BRIGHTDATA_COLLECTOR_ID` (the `c_*` ID once created)
- `DISCORD_WEBHOOK_URL`
- Store in `.env` locally (gitignored) and as GitHub Actions secrets in CI.
  Never expose these in the repo or in a demo/screen share.

## Success criteria
- Scraper runs on schedule and returns clean per-product JSON.
- A real discount change on the site produces a Discord message within one
  scheduled run.
- A simulated site-structure break is detected (not silently treated as
  "no discounts"), triggers `bdata scraper heal`, gets fixed, gets
  re-verified, and normal collection resumes — all without editing the
  diff/storage/Discord code.
- Collector ID stays constant across the entire demo.

## Best practices carried over
- **Long tail target**: confirm no pre-built Bright Data scraper already
  covers this site before starting.
- **Terminal-first**: drive scraper create/run/heal from the CLI agent;
  only use the Bright Data dashboard to look up the Collector ID or set up
  a schedule if the CLI doesn't cover it.
- **Show the heal, don't hide it**: the demo should include a real or
  simulated break + `bdata scraper heal` + successful resume — this is the
  differentiator, not the scraper itself.
- **Public data only**: no login-walled pages, no paywalled content, no
  personal data.
- **Treat the Collector ID as your API**: everything downstream (storage,
  diff, Discord) talks to `c_*` via `POST /dca/trigger`, never to raw
  scraping logic directly.