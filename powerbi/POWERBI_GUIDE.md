# Power BI Companion — Build Guide

This guide turns the warehouse's exported marts into a polished, 6-page Power BI
report with a proper star-schema model, the six headline KPIs, and the flagship
"12% → 38%" segmentation story. It is the boardroom-facing twin of the Streamlit
self-serve app — same numbers, same single source of truth (`data/exports/`).

> **Why file extracts and not a live Snowflake connection?**
> This project runs entirely on a free, local stack. The pipeline materialises
> the marts to `data/exports/` as **both `.csv` (universally importable)** and
> **`.parquet` (typed & compressed)** on every run. Power BI connects to that
> folder. In a paid deployment you would instead point Power BI's native
> connector at the warehouse; the model and DAX below are identical either way.

---

## 0. Prerequisites

1. Run the pipeline so the extracts exist:

   ```bash
   python src/orchestrate.py
   ```

   Confirm these files exist under `data/exports/`:
   `dim_customers`, `dim_date`, `fct_orders`, `fct_subscriptions`,
   `kpi_daily`, `kpi_monthly`, `customer_segments`, `cohort_retention`
   (each as `.csv` **and** `.parquet`), plus `_manifest.json`.

2. Install **Power BI Desktop** (free, Windows).

---

## 1. Import the extracts

**Home ▸ Get Data ▸ Folder** → point at `…/operational-data-warehouse/data/exports`.

- Choose **Transform Data** to open Power Query.
- For a folder import, filter to the `.parquet` rows (better types) or simply use
  **Get Data ▸ Parquet** once per table. The cleanest path for a first build is:
  **Get Data ▸ Text/CSV** and import each of the 8 CSVs individually — Power BI
  infers types well because the exporter writes clean, typed columns.
- In Power Query, verify data types (dates as *Date*, money as *Decimal*,
  rates as *Decimal*), then **Close & Apply**.

---

## 2. Build the star schema (Model view)

Create these relationships (single-direction, one-to-many from dimension → fact):

| From (one side)              | To (many side)                         | Cardinality |
|------------------------------|----------------------------------------|-------------|
| `dim_date[date_key]`         | `fct_orders[order_date]`               | 1 → *       |
| `dim_date[date_key]`         | `kpi_daily[date_key]`                  | 1 → *       |
| `dim_customers[customer_id]` | `fct_orders[customer_id]`              | 1 → *       |
| `dim_customers[customer_id]` | `fct_subscriptions[customer_id]`       | 1 → *       |
| `dim_customers[customer_id]` | `customer_segments[customer_id]`       | 1 → 1       |

- Mark **`dim_date`** as a date table: *Table tools ▸ Mark as date table* → `date_key`.
- `kpi_monthly` and `cohort_retention` are **pre-aggregated** marts; keep them as
  standalone tables (no relationship needed) and drive their visuals directly.
  This is deliberate — the heavy KPI math (churn, CAC, LTV, retention) is already
  computed in dbt so the report stays fast and the logic stays in one place.

---

## 3. Add the measures

Create an empty table named **`_Measures`** (*Home ▸ Enter Data*), then paste each
measure from [`measures.dax`](measures.dax) via *Modeling ▸ New measure*. They are
grouped by KPI and ready to use.

---

## 4. Report pages (6 KPIs + the story)

### Page 1 — Executive Scorecard
- **6 KPI cards** across the top using: `[Recognized Revenue]`, `[Churn Rate]`,
  `[CAC]`, `[LTV]` (+ `[LTV to CAC Ratio]` as callout), `[Conversion Rate]`,
  `[Retention 30d (Latest)]`.
- Apply **conditional formatting** on each card's background using the RAG
  measures (`[Revenue RAG]`, `[LTV CAC Status]`, …): green ≥ target, amber near,
  red below.
- **Combo chart**: X = `kpi_monthly[month]`, columns = `[Recognized Revenue]`,
  line (secondary axis) = `[Active MRR]`. Add a constant line at 500,000.
- **KPI matrix**: rows = `kpi_monthly[month_label]`, values = all six KPIs
  (last 12 months).

### Page 2 — Revenue & Growth
- Column chart of `[Recognized Revenue]` by `dim_date[month_start]`.
- `[Recognized Revenue]` by `dim_customers[region]` (bar) and by
  `dim_customers[plan]` (donut).
- Cards for `[Avg Order Value]`, `[Refund Rate]`, `[Revenue YTD]`,
  `[Revenue MoM %]`.

### Page 3 — Customer Segments  *(the flagship page)*
- **Big number card**: `[Priority Concentration Label]` →
  renders *"12% of customers → 38% of revenue"*.
- **100% stacked bar**: `customer_segments[value_tier]` share of `[Total Segment
  Revenue]` vs share of customer count — the visual proof of concentration.
- **Pareto (line + column combo)**: customers sorted by `lifetime_revenue`
  descending on X, cumulative revenue % on the line; add reference line at the
  top-12% mark.
- **Table**: top 25 customers by `lifetime_revenue` with `value_tier`, `region`,
  `plan`, `revenue_share`.
- **RFM matrix**: rows = `m_score`, columns = `f_score`, values = customer count,
  background = heat.

### Page 4 — Retention & Cohorts
- **Matrix heatmap**: rows = `cohort_retention[cohort_label]`, columns =
  `months_since_signup`, values = `AVERAGE(retention_rate)`, background color
  scale 0→1. This is the classic cohort triangle.
- **Retention curve**: line of average `retention_rate` by `months_since_signup`.
- **Churn by plan**: bar of `fct_subscriptions` churn share by `plan`.

### Page 5 — Acquisition & Conversion
- **Funnel**: page views → sessions → conversions → new customers.
- `[Conversion Rate]` by channel (bar).
- `[Marketing Spend]` by channel × region (stacked).
- **CAC vs LTV** dual-line over `kpi_monthly[month]`; add `[LTV to CAC Ratio]`
  as a KPI card with `[LTV CAC Status]` conditional formatting.

### Page 6 — Self-Serve / Drillthrough
- A slicer panel (Region, Plan, Channel, Date) synced across pages.
- A drillthrough page keyed on `customer_id` showing that customer's orders,
  subscription, tier and lifetime value.

---

## 5. Interactivity & polish

- **Sync slicers** (View ▸ Sync slicers) for Region / Plan / Channel / Date across
  pages 1–5 so the whole report filters together — the same global-filter behaviour
  as the Streamlit app.
- Add **bookmarks** for "Board view" (KPIs only) vs "Analyst view" (all detail).
- Theme: dark canvas, one accent color (`#2563eb`), consistent card style.

---

## 6. Scheduled refresh (free tier)

Because the source is a local folder, refresh is driven by re-running the pipeline:

1. `python src/orchestrate.py` regenerates and re-exports the marts.
2. In Power BI Desktop, **Home ▸ Refresh** re-reads the folder.
3. To automate the daily cadence, schedule the pipeline (see the repo README's
   *Scheduling* section — Windows Task Scheduler / `cron`), then publish to the
   Power BI Service and configure a Personal Gateway pointed at the exports folder
   for scheduled cloud refresh.

The daily refresh is what replaces **~5 hours/week** of manual spreadsheet
reporting: the numbers on every page are recomputed and re-tested end-to-end
before they ever reach a stakeholder.
