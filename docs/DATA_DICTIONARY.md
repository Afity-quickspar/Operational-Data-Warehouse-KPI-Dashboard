# Data Dictionary

Every table and key column in the warehouse, by layer. Schemas in DuckDB:
`raw` (landed), `main_staging` (dbt views), `main_marts` (dbt tables).

---

## Layer 1 — `raw` (landed source extracts)

Loaded 1:1 from `data/raw/` by [`src/ingest.py`](../src/ingest.py). Each table
carries an `_ingested_at` timestamp used as the freshness anchor.

### `raw.customers`  (CSV) — 8,000 rows
| Column | Type | Description |
|---|---|---|
| customer_id | BIGINT | Surrogate customer key (100000+) |
| customer_name | VARCHAR | Company name |
| email | VARCHAR | Contact email (~1.5% intentionally blank for null-rate testing) |
| signup_date | DATE | Account creation date |
| region | VARCHAR | North America / EMEA / APAC / LATAM |
| country | VARCHAR | ISO country code |
| acquisition_channel | VARCHAR | First-touch marketing channel |
| plan | VARCHAR | Free / Starter / Pro / Business / Enterprise |
| company_size | INT | Employee band (5–2500) |
| industry | VARCHAR | Vertical |
| is_high_value_seed | INT | Ground-truth priority-segment label (0/1) |

### `raw.orders`  (CSV) — 62,642 rows
| Column | Type | Description |
|---|---|---|
| order_id | BIGINT | Order key |
| customer_id | BIGINT | FK → customers |
| order_ts | TIMESTAMP | Order timestamp |
| gross_amount | DOUBLE | Pre-discount amount |
| discount_pct | DOUBLE | Discount fraction (0–0.20) |
| net_amount | DOUBLE | `gross_amount × (1 − discount_pct)` |
| num_items | INT | Line items |
| channel | VARCHAR | Order channel |
| status | VARCHAR | completed / refunded / pending |

### `raw.subscriptions`  (CSV) — 8,000 rows
| Column | Type | Description |
|---|---|---|
| subscription_id | BIGINT | Subscription key |
| customer_id | BIGINT | FK → customers |
| plan | VARCHAR | Plan tier |
| mrr | DOUBLE | Monthly recurring revenue for the plan |
| start_date | DATE | Subscription start |
| status | VARCHAR | active / churned / paused |
| churn_date | DATE | Date churned (blank if not churned) |
| months_active | INT | Months before churn / to date |
| billing_interval | VARCHAR | monthly / annual |

### `raw.web_sessions`  (CSV) — 22,000 rows
| Column | Type | Description |
|---|---|---|
| session_id | VARCHAR | Session key |
| session_ts | TIMESTAMP | Session start |
| channel | VARCHAR | Traffic channel |
| device | VARCHAR | desktop / mobile / tablet |
| landing_page | VARCHAR | Entry page |
| pages_viewed | INT | Pages in session |
| duration_sec | INT | Session length |
| converted | INT | 1 if the session converted to signup |
| customer_id | BIGINT | FK → customers (only when converted) |

### `raw.marketing_spend`  (CSV) — 640 rows
| Column | Type | Description |
|---|---|---|
| spend_date | DATE | Month start |
| channel | VARCHAR | Paid channel (Organic/Direct excluded — no spend) |
| region | VARCHAR | Region |
| spend | DOUBLE | Ad spend |
| impressions | BIGINT | Impressions |
| clicks | BIGINT | Clicks |

### `raw.events`  (JSON, flattened) — ~185,000 rows
| Column | Type | Description |
|---|---|---|
| event_id | BIGINT | Event key |
| customer_id | BIGINT | FK → customers |
| event_type | VARCHAR | page_view / feature_used / activation / … |
| event_ts | TIMESTAMP | Event time |
| platform | VARCHAR | web / ios / android / api (from JSON `properties`) |
| app_version | VARCHAR | From JSON `properties` |
| session_len_sec | BIGINT | From JSON `properties` |
| feature | VARCHAR | Feature area (from JSON `properties`) |

---

## Layer 2 — `main_staging` (typed, cleansed views)

`stg_customers`, `stg_orders`, `stg_subscriptions`, `stg_web_sessions`,
`stg_marketing_spend`, `stg_events`. These cast types, standardise nulls, and
add derived flags — e.g. `stg_orders.recognized_revenue` (net_amount when
completed, else 0) and `is_recognized`; `stg_subscriptions.is_churned` /
`is_active`; `stg_customers.segment_band` (SMB / Mid-Market / Enterprise).

---

## Layer 3 — `main_marts` (star schema + KPI marts)

### Dimensions
- **`dim_date`** — conformed calendar (one row/day): `date_key`, `year`,
  `quarter`, `month_num`, `month_name`, `month_start`, `week_num`, `day_name`,
  `is_weekend`.
- **`dim_customers`** — wide customer record: CRM attributes + `lifetime_orders`,
  `lifetime_revenue`, `avg_order_value`, `mrr`, `has_active_sub`, `has_churned`,
  `tenure_months`, `lifetime_events`, `recency_days`.

### Facts
- **`fct_orders`** — order grain enriched with region/plan/segment/channel and
  `recognized_revenue`.
- **`fct_subscriptions`** — subscription grain with `mrr`, `arr`, `cohort_month`,
  churn flags.

### KPI / analytical marts
- **`kpi_daily`** — one row/day: revenue, orders, new customers, sessions,
  conversions, conversion_rate, product_events.
- **`kpi_monthly`** — one row/month with all **six KPIs** plus supporting
  measures (`active_mrr`, `arpa`, `refund_rate`, `cohort_is_mature`, …).
- **`customer_segments`** — per-customer RFM scores, `value_tier`
  (High-Value/Core/Occasional/Dormant), `priority_segment`, and the
  concentration columns `priority_revenue_share` / `priority_customer_share`.
- **`cohort_retention`** — signup-cohort × months-since-signup retention rate.

---

## Exports — `data/exports/`

Eight marts materialised as `.csv` **and** `.parquet` on every run, plus
`_manifest.json` (row counts + generation timestamp). These are the Power BI
and portable-analysis inputs.
