# Architecture & Design Notes

A deeper look at *why* the pipeline is built the way it is, and the engineering
decisions behind each layer.

---

## Design principles

1. **ELT, not ETL.** Land data faithfully first (`raw.*`), then transform inside
   the warehouse with SQL/dbt. Raw stays immutable and re-runnable; all business
   logic is version-controlled SQL.
2. **One source of truth for every metric.** Churn, CAC, LTV, retention and the
   priority segment are defined **once** in dbt marts. Power BI and Streamlit both
   read those marts — they never re-derive a KPI, so the two tools can't disagree.
3. **Tested data, gated releases.** 57 dbt tests + 6 freshness checks run on every
   pipeline execution; the orchestrator skips exports and fails the run if they
   don't pass.
4. **Deterministic & reproducible.** Seeded generation means identical output
   across machines and runs — essential for stable tests and demos.
5. **Free & local by construction.** DuckDB replaces Snowflake; a custom Python
   DAG replaces Airflow; dbt-core replaces dbt Cloud. Same shape, zero license.

---

## Why DuckDB (instead of Snowflake)

- **Columnar OLAP engine** with vectorized execution — the right shape for
  analytical aggregations over hundreds of thousands of rows.
- **ANSI SQL + window functions + `FILTER` + `QUALIFY`** — the dbt models port to
  Snowflake/BigQuery with minimal change.
- **Embedded, single-file** (`warehouse.duckdb`) — no server, no cost, trivial to
  reset (`make clean`).
- **First-class dbt adapter** (`dbt-duckdb`) and native readers for CSV, JSON and
  Parquet — which is exactly what the ingestion and export layers lean on.

At production scale you swap the DuckDB profile for a Snowflake/BigQuery profile;
the models, tests and orchestration are unchanged.

## Why a custom Python DAG (instead of Airflow)

Airflow is excellent but heavy (scheduler, webserver, metadata DB) and is the one
piece of the reference stack that's operationally costly to run locally. The
orchestrator in [`src/orchestrate.py`](../src/orchestrate.py) reproduces the parts
that matter for this project:

- **A real DAG** — tasks declare `upstream` dependencies and execute in
  topological order, with cycle detection.
- **Retries with backoff** per task.
- **Skip-on-upstream-failure** semantics (a failed test skips export + report).
- **Freshness gate** wired as a task between `dbt_run` and `export`.
- **Observability** — per-task timing, structured logs to `data/logs/`, and a
  markdown **run report** artefact per execution.

The public interface (`--skip-generate`, `--no-freshness`) mirrors how you'd
parameterise an Airflow DAG run.

---

## Modeling: the star schema

```
                         dim_date
                            │
                            ▼
   dim_customers ─────▶ fct_orders
        │                   
        ├──────────────▶ fct_subscriptions
        │
        └──────────────▶ customer_segments (1:1)
```

- **Conformed dimensions** (`dim_date`, `dim_customers`) are shared across facts.
- **Facts** are at their natural grain (order, subscription).
- **KPI marts** (`kpi_daily`, `kpi_monthly`) are *pre-aggregated* so BI tools stay
  fast and the metric math lives in one tested place rather than in DAX/Python.
- **`customer_segments`** is 1:1 with customers and carries both the analytical
  RFM tiering and the strategic `priority_segment` flag.

---

## The flagship segmentation ("12% → 38%")

The high-value cohort is defined at generation time by real, business-plausible
drivers (plan mix, order frequency ~2×, AOV ~2.25×) and carried as
`is_high_value_seed`. In the warehouse it becomes
`customer_segments.priority_segment`, and the model computes the concentration
directly:

```sql
priority_revenue_share =
    Σ lifetime_revenue where priority_segment = 1  /  Σ lifetime_revenue
```

This run: **12.0% of customers → 37.8% of revenue.** A parallel, independent RFM
`value_tier` (deciles) corroborates it — the top revenue decile alone accounts
for ~39% of revenue (see `sql/analysis/kpi_analysis.sql`, query 2).

Because the flag lives in the warehouse, the "target this segment" decision is
consistent everywhere: the Streamlit banner, the Power BI card, and any SQL
consumer all read the same definition.

---

## Retention methodology (why it doesn't saturate)

Naive "ever active after day 30" retention saturates to ~100% because engaged
users keep generating events forever. Two design choices make 30-day retention a
*real* signal:

1. **Disengagement is modeled.** ~35% of customers are "early-drop": their product
   events cluster in the first ≤30 days and then stop — exactly how churned users
   behave. Retention therefore measures who *came back*, not who *ever existed*.
2. **A fixed return window + maturity gate.** Retention = share of a signup cohort
   with a product event in the **[day 30, day 60)** window; cohorts whose 60-day
   window hasn't fully elapsed are flagged `cohort_is_mature = false` and excluded
   from the headline. Result: a realistic ~55–68% that declines along the cohort
   curve.

---

## Data quality strategy

| Test type | Where | Example |
|---|---|---|
| Uniqueness / not-null | every PK | `order_id`, `customer_id`, `date_key` |
| Referential integrity | fact → dim | `fct_orders.customer_id → dim_customers` |
| Domain / accepted values | staging + marts | `status ∈ {completed,refunded,pending}` |
| Range / bounds (singular) | tests/ | `net_amount ≥ 0`, `churn_rate ∈ [0,1]` |
| Reconciliation (singular) | tests/ | daily recognized revenue = order-grain revenue |
| Freshness SLA | sources | WARN 36h / ERROR 72h on `_ingested_at` |

---

## Scaling & extension ideas

- **More volume:** raise `generation.customers` / `avg_orders_per_customer` in the
  config — the pipeline and tests scale unchanged.
- **Real warehouse:** copy a target from
  [`profiles.cloud.example.yml`](../dbt/warehouse_dbt/profiles.cloud.example.yml)
  into `profiles.yml`, set the matching vars from
  [`.env.example`](../.env.example), and run `dbt build --target prod_snowflake`
  (or `prod_bigquery`) — the models and tests are unchanged.
- **Incremental models:** `fct_orders` is already a dbt incremental model
  (`unique_key='order_id'`, `delete+insert`, filtered on `order_ts` past the max
  already loaded) — the pattern to copy for other large, append-only facts.
  Force a rebuild with `dbt run --full-refresh --select fct_orders`.
- **Semantic layer:** add a dbt Semantic Layer / MetricFlow definition so the six
  KPIs are queryable as governed metrics.
- **Alerting:** extend the orchestrator's run report to post failures to Slack/email.
- **CI:** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs the full
  pipeline (generate → ingest → dbt build → freshness) on every push/PR, so a
  broken model or a failing test is caught before merge, not on the next local run.

### Orchestrator concurrency

`src/orchestrate.py`'s `DAG.run()` executes tasks in **waves**: any task whose
upstream has fully resolved runs immediately, and independent tasks within a
wave run concurrently via a thread pool — real Airflow-style fan-out rather
than one-task-at-a-time. In the current DAG this mostly doesn't change wall
clock, because `dbt_test` and `dbt_source_freshness` are deliberately chained
(`dbt_source_freshness` depends on `dbt_test`, not just `dbt_run`) rather than
left to run in the same wave: DuckDB is a single-writer embedded engine, and
two concurrent dbt invocations against the same `.duckdb` file both open a
read-write connection and would race for the file lock (the `IO Error: File is
already open` failure mode described below). The wave executor is written
generically so a task set with genuinely independent, non-file-contending work
(e.g. exporting to per-table files, or calling external APIs) gets real
parallelism for free.
