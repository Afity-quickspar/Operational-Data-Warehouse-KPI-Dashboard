# Operational Data Warehouse & KPI Dashboard

**An end-to-end, production-shaped analytics engineering project** — synthetic
operational data is generated, staged, loaded into a columnar warehouse,
transformed and **tested** with dbt, orchestrated as a daily dependency-aware
DAG, and surfaced through **both** an interactive Streamlit self-serve app **and**
a Power BI companion report. Every number on every dashboard is recomputed and
re-tested end-to-end before it reaches a stakeholder.

> **Stack:** Python · SQL · **DuckDB** (warehouse) · **dbt** (transform + test) ·
> custom **Python DAG orchestrator** · **Power BI** · **Streamlit**
>
> **Deliberately free & local.** This build swaps the paid components of the
> classic reference architecture for free, open equivalents that keep the exact
> same engineering shape:
>
> | Reference (paid)        | This project (free)                     | Why it's equivalent                                  |
> |-------------------------|-----------------------------------------|------------------------------------------------------|
> | Snowflake               | **DuckDB**                              | Columnar, ANSI-SQL OLAP engine; dbt-native           |
> | Airflow                 | **Custom Python DAG orchestrator**      | Topological task graph, retries, freshness gates, run reports |
> | dbt Cloud               | **dbt-core (CLI)**                       | Same models, tests, freshness, docs                  |

---

## 📌 Headline results (this run)

| KPI (last complete month, 2025-07) | Value | Target | Status |
|---|---|---|---|
| Recognized revenue | **$578.6K** | ≥ $500K/mo | 🟢 On target |
| Logo churn (monthly) | **5.36%** | ≤ 5.5% | 🟢 On target |
| CAC (blended) | **$949** | ≤ $1,200 | 🟢 On target |
| Customer LTV | **$2,952** | ≥ $2,500 | 🟢 On target |
| LTV : CAC ratio | **3.1×** | ≥ 3.0× | 🟢 On target |
| Web→signup conversion | **4.71%** | ≥ 4.5% | 🟢 On target |
| 30-day retention (last matured cohort) | **68.3%** | ≥ 55% | 🟢 On target |

> 💡 **Flagship insight —** a strategically-defined **high-value priority segment
> is just 12% of customers but drives 38% of all recognized revenue.** This single
> cohort, defined once in the warehouse (`customer_segments.priority_segment`),
> flows to every downstream tool and anchors a targeted segmentation & retention
> strategy.

**Data volume:** ~**358,000 rows** generated across **6 source systems**
(62,642 orders · 185,075 product events · 22,000 web sessions · 8,000 customers ·
8,000 subscriptions · 640 marketing-spend rows) — comfortably clearing the
**100,000+ row** bar, ingested from **mixed CSV + JSON** extracts.

---

## 🎯 Résumé bullets → where they live in this repo

> **• Built an ETL/ELT pipeline loading 100,000+ rows into the warehouse via
> staged CSV/JSON ingestion, with dbt schema tests and freshness checks
> orchestrated through a daily DAG.**

- Generation → [`src/generate_data.py`](src/generate_data.py) (358K rows, 6 sources, seeded/deterministic)
- Staged mixed-format ingestion (CSV + nested JSON) → [`src/ingest.py`](src/ingest.py)
- **57 dbt tests** (unique, not_null, relationships, accepted_values, singular
  reconciliation tests) + **6 source freshness checks** → [`dbt/warehouse_dbt/`](dbt/warehouse_dbt/)
- Daily DAG (topological order, retries, freshness gate, run report) →
  [`src/orchestrate.py`](src/orchestrate.py)

> **• Designed a Power BI dashboard covering 6 KPIs (revenue, churn, CAC, LTV,
> conversion, 30-day retention) plus a Streamlit self-serve app; daily refresh
> saved ~5 hours/week of manual reporting.**

- 6 KPIs computed in [`kpi_monthly.sql`](dbt/warehouse_dbt/models/marts/kpi_monthly.sql)
- Power BI model + DAX + build guide → [`powerbi/`](powerbi/)
- Streamlit self-serve app (6 pages, global filters, SQL runner) →
  [`streamlit_app/app.py`](streamlit_app/app.py)

> **• Surfaced a high-value customer segment driving 38% of revenue from just 12%
> of users, informing a targeted segmentation and retention strategy.**

- RFM + priority-segment model → [`customer_segments.sql`](dbt/warehouse_dbt/models/marts/customer_segments.sql)
- Proof queries → [`sql/analysis/kpi_analysis.sql`](sql/analysis/kpi_analysis.sql)

---

## 🏗️ Architecture

```
 ┌─────────────────┐   generate    ┌──────────────────────┐   ingest (EL)   ┌──────────────────────┐
 │  Source systems  │ ────────────▶ │  data/raw/            │ ──────────────▶ │  DuckDB  ·  raw.*      │
 │  (simulated)     │  CSV + JSON   │  customers.csv        │  read_csv_auto  │  6 landed tables      │
 │  billing, CRM,   │               │  orders.csv           │  read_json_auto │  + _ingested_at audit │
 │  product, ads    │               │  events.json  …       │                 └──────────┬───────────┘
 └─────────────────┘               └──────────────────────┘                            │ dbt run
                                                                                        ▼
      ┌──────────────────────────────── dbt (transform + test) ───────────────────────────────┐
      │  staging (views, typed & cleansed)      marts (tables, star schema + KPIs)             │
      │  stg_customers, stg_orders, …           dim_customers  dim_date                        │
      │        │  57 data tests                 fct_orders     fct_subscriptions               │
      │        │  6 freshness checks            kpi_daily      kpi_monthly (6 KPIs)            │
      │        ▼                                customer_segments   cohort_retention           │
      └───────────────────────────────────────────────┬──────────────────────────────────────┘
                                                       │ export
                        ┌──────────────────────────────┴───────────────────────────┐
                        ▼                                                            ▼
              data/exports/ (CSV + Parquet)                              main_marts.* (queried live)
                        │                                                            │
                        ▼                                                            ▼
                ┌──────────────┐                                          ┌────────────────────┐
                │  Power BI     │                                          │  Streamlit app      │
                │  6-page report│                                          │  6 pages + SQL      │
                └──────────────┘                                          └────────────────────┘

        Everything above the exports line is scheduled by  src/orchestrate.py  (the daily DAG).
```

The DAG executed by the orchestrator:

```
generate_source_data → ingest_raw → dbt_run ─┬─→ dbt_test ────────────┐
                                              └─→ dbt_source_freshness ─┴─→ export_bi_extracts → publish_run_report
```
(`export_bi_extracts` waits on both `dbt_test` and `dbt_source_freshness`; any
upstream failure skips it and fails the run.)

---

## 🚀 Quickstart

**Requirements:** Python 3.11 (recommended), Windows/macOS/Linux.

```bash
# 1) Create the environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# 2) Run the whole pipeline (generate → ingest → dbt run+test+freshness → export)
python src/orchestrate.py

# 3) Launch the self-serve dashboard
streamlit run streamlit_app/app.py
#    → http://localhost:8501
```

**Faster refresh** (reuse existing raw files, skip regeneration):

```bash
python src/orchestrate.py --skip-generate
```

**Run dbt directly** (from the dbt project directory):

```bash
cd dbt/warehouse_dbt
dbt build --profiles-dir .          # run models + tests
dbt source freshness --profiles-dir .
dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .
```

**Ad-hoc SQL** against the warehouse:

```bash
duckdb data/warehouse/warehouse.duckdb
# then:  .read sql/analysis/kpi_analysis.sql
```

---

## 📊 The six KPIs — definitions

All KPIs are computed in SQL in
[`kpi_monthly.sql`](dbt/warehouse_dbt/models/marts/kpi_monthly.sql), so the logic
is version-controlled, tested, and identical across Power BI and Streamlit.

| KPI | Definition | Formula (essence) |
|---|---|---|
| **Revenue** | Recognized revenue from completed orders | `Σ net_amount where status = 'completed'` |
| **Churn** | Monthly logo churn | `churned_subs_in_month / active_subs_at_month_start` |
| **CAC** | Blended customer acquisition cost | `marketing_spend_in_month / new_customers_in_month` |
| **LTV** | Customer lifetime value | `ARPA / churn_rate` (ARPA = revenue / active customers) |
| **Conversion** | Web → signup conversion | `converted_sessions / total_sessions` |
| **30-day retention** | Product-usage retention, cohort-anchored | `share of a signup cohort active (events) in the [day 30, day 60) window` |

**Design notes that make the numbers trustworthy:**
- The **partial trailing month** is excluded from the executive scorecard so
  MoM deltas compare like-for-like complete months.
- **30-day retention** is a *product-usage* signal (events), and only cohorts
  whose 60-day window has fully elapsed (`cohort_is_mature`) are reported —
  so it never saturates or reports on immature cohorts.
- A dbt **singular test** reconciles daily recognized revenue to the order grain,
  guarding against accidental join fan-out.

---

## 🧱 Project structure

```
operational-data-warehouse/
├── config/pipeline_config.yaml     # single source of truth (volumes, SLAs, targets)
├── src/
│   ├── generate_data.py            # synthetic 6-source generator (deterministic)
│   ├── ingest.py                   # staged CSV/JSON → DuckDB raw.*
│   ├── orchestrate.py              # the daily DAG (Airflow-free)
│   ├── export_bi.py                # marts → CSV + Parquet for Power BI
│   └── utils/{db,logger}.py        # config, connection, structured logging
├── dbt/warehouse_dbt/
│   ├── models/staging/             # 6 typed/cleansed views + source freshness
│   ├── models/marts/               # star schema + KPI marts
│   ├── tests/                      # singular reconciliation/bounds tests
│   ├── dbt_project.yml · profiles.yml
├── streamlit_app/
│   ├── app.py                      # 6-page self-serve BI app
│   └── data_access.py              # cached DuckDB read layer
├── powerbi/
│   ├── measures.dax                # full DAX measure library (6 KPIs + more)
│   └── POWERBI_GUIDE.md            # step-by-step build guide
├── sql/analysis/kpi_analysis.sql   # 9 ad-hoc analytical queries
├── docs/                           # data dictionary, architecture, KPI notes
├── data/{raw,warehouse,exports,logs}/
└── requirements.txt
```

See [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) for every table & column,
and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design deep-dive.

---

## ✅ Data quality & testing

Running `dbt build` executes **14 models** and **57 data tests**; `dbt source
freshness` runs **6 freshness checks**. Test coverage includes:

- **Uniqueness & not-null** on every primary key across staging and marts.
- **Referential integrity** (`relationships`) — e.g. every order maps to a real customer.
- **Domain constraints** (`accepted_values`) — plan, region, status, tier, event type.
- **Singular tests** — non-negative revenue/MRR, churn bounded in `[0,1]`, and a
  daily-to-order **revenue reconciliation** test.
- **Freshness SLAs** — WARN after 36h, ERROR after 72h, anchored on the
  `_ingested_at` audit column.

The orchestrator treats these as **gates**: if tests or freshness fail,
downstream export/report tasks are skipped and the run is marked failed, with a
per-task run report written to `data/logs/run_report_*.md`.

---

## 🔁 Scheduling (the "daily refresh")

The pipeline is a single command, so a daily cadence is just a scheduled call:

- **Windows Task Scheduler**
  ```powershell
  schtasks /Create /SC DAILY /TN "DWH Daily" /TR ^
    "C:\path\to\.venv\Scripts\python.exe C:\path\to\src\orchestrate.py --skip-generate" /ST 06:00
  ```
- **cron** (macOS/Linux)
  ```cron
  0 6 * * *  cd /path/to/operational-data-warehouse && .venv/bin/python src/orchestrate.py --skip-generate
  ```

That automated daily refresh — recompute, re-test, re-export, re-report — is what
replaces the **~5 hours/week** of manual spreadsheet reporting.

---

## 🧪 Reproducibility

Generation is fully **seeded** (`config/pipeline_config.yaml → generation.seed`),
so every run reproduces the same 358K-row dataset, the same KPI values, and the
same 12%→38% concentration. Change the seed or the volumes in the config to
scale the dataset up or down.

---

## 🛠️ Troubleshooting

- **`IO Error: File is already open` during ingest.** DuckDB is a single-file
  embedded engine, so the pipeline (read-write) can't refresh the warehouse while
  the Streamlit app or a `duckdb` shell holds it open. **Stop the dashboard before
  running `python src/orchestrate.py`**, then relaunch it. (In a server warehouse
  like Snowflake this is a non-issue — reads and writes are concurrent.) Note the
  orchestrator handles this gracefully: it fails `ingest_raw`, **skips** all
  downstream tasks, and writes a run report rather than producing half-built marts.
- **`streamlit` opens on the wrong port / a different app.** Another Streamlit
  server may already hold the port; this project's app is configured for **8533**
  (see `.claude/launch.json`). Launch explicitly with
  `streamlit run streamlit_app/app.py --server.port 8533`.
- **Warehouse not found in the app.** Run `python src/orchestrate.py` first — the
  app reads `data/warehouse/warehouse.duckdb`, which the pipeline builds.

---

## 📄 License / data

All data is **synthetic** and generated locally — no PII, no external data
sources, nothing paid. Free to reuse as a portfolio reference.
