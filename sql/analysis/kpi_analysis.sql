-- ============================================================================
--  AD-HOC ANALYTICAL SQL  (DuckDB dialect)
--  Run against the warehouse:  data/warehouse/warehouse.duckdb
--  These queries power the "how did we arrive at the number" narrative behind
--  each dashboard tile and are safe to run read-only.
--
--  Quick start:
--    duckdb data/warehouse/warehouse.duckdb
--    .read sql/analysis/kpi_analysis.sql
-- ============================================================================


-- ─────────────────────────────────────────────────────────────────────────
-- 1. FLAGSHIP: revenue concentration — the priority segment ("12% -> 38%")
-- ─────────────────────────────────────────────────────────────────────────
SELECT
    CASE WHEN priority_segment = 1 THEN 'Priority (high-value)' ELSE 'Everyone else' END AS cohort,
    COUNT(*)                                             AS customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)   AS pct_customers,
    ROUND(SUM(lifetime_revenue))                         AS lifetime_revenue,
    ROUND(100.0 * SUM(lifetime_revenue)
                / SUM(SUM(lifetime_revenue)) OVER (), 1) AS pct_revenue
FROM main_marts.customer_segments
GROUP BY 1
ORDER BY pct_revenue DESC;


-- ─────────────────────────────────────────────────────────────────────────
-- 2. Pareto check: what share of revenue comes from the top-N% of customers?
-- ─────────────────────────────────────────────────────────────────────────
WITH ranked AS (
    SELECT
        customer_id,
        lifetime_revenue,
        SUM(lifetime_revenue) OVER (ORDER BY lifetime_revenue DESC
                                    ROWS UNBOUNDED PRECEDING) AS running_rev,
        SUM(lifetime_revenue) OVER ()                         AS total_rev,
        ROW_NUMBER() OVER (ORDER BY lifetime_revenue DESC)    AS rn,
        COUNT(*) OVER ()                                      AS total_cust
    FROM main_marts.customer_segments
)
SELECT
    pct_bucket || '%'                                        AS top_customers,
    ROUND(100.0 * MAX(running_rev) / MAX(total_rev), 1)      AS pct_of_revenue
FROM (
    SELECT *, CAST(CEIL(10.0 * rn / total_cust) * 10 AS INT) AS pct_bucket
    FROM ranked
)
WHERE pct_bucket IN (10, 20, 30, 50)
GROUP BY pct_bucket
ORDER BY pct_bucket;


-- ─────────────────────────────────────────────────────────────────────────
-- 3. The six KPIs, latest complete month vs. prior month
-- ─────────────────────────────────────────────────────────────────────────
WITH complete AS (
    SELECT *
    FROM main_marts.kpi_monthly
    WHERE month < date_trunc('month',
        (SELECT MAX(order_date) FROM main_marts.fct_orders))
    ORDER BY month DESC
    LIMIT 2
)
SELECT
    month_label,
    ROUND(recognized_revenue)          AS revenue,
    ROUND(churn_rate, 4)               AS churn_rate,
    ROUND(cac)                         AS cac,
    ROUND(ltv)                         AS ltv,
    ROUND(ltv / NULLIF(cac, 0), 2)     AS ltv_cac_ratio,
    ROUND(conversion_rate, 4)          AS conversion_rate,
    ROUND(retention_30d, 4)            AS retention_30d
FROM complete
ORDER BY month_label;


-- ─────────────────────────────────────────────────────────────────────────
-- 4. Revenue bridge: month-over-month growth and 3-month moving average
-- ─────────────────────────────────────────────────────────────────────────
SELECT
    month_label,
    ROUND(recognized_revenue)                                        AS revenue,
    ROUND(recognized_revenue - LAG(recognized_revenue)
          OVER (ORDER BY month))                                     AS mom_delta,
    ROUND(100.0 * (recognized_revenue - LAG(recognized_revenue) OVER (ORDER BY month))
          / NULLIF(LAG(recognized_revenue) OVER (ORDER BY month), 0), 1) AS mom_pct,
    ROUND(AVG(recognized_revenue) OVER (ORDER BY month
          ROWS BETWEEN 2 PRECEDING AND CURRENT ROW))                 AS rev_3mo_avg
FROM main_marts.kpi_monthly
ORDER BY month;


-- ─────────────────────────────────────────────────────────────────────────
-- 5. Channel efficiency: spend, acquired customers, blended CAC, revenue ROAS
-- ─────────────────────────────────────────────────────────────────────────
WITH spend AS (
    SELECT channel, SUM(spend) AS spend
    FROM main_staging.stg_marketing_spend GROUP BY 1
),
rev AS (
    SELECT acquisition_channel AS channel,
           SUM(recognized_revenue) AS revenue,
           COUNT(DISTINCT customer_id) AS customers
    FROM main_marts.fct_orders GROUP BY 1
)
SELECT
    r.channel,
    r.customers,
    ROUND(COALESCE(s.spend, 0))                       AS marketing_spend,
    ROUND(COALESCE(s.spend, 0) / NULLIF(r.customers, 0)) AS cac,
    ROUND(r.revenue)                                  AS revenue,
    ROUND(r.revenue / NULLIF(s.spend, 0), 2)          AS roas
FROM rev r
LEFT JOIN spend s USING (channel)
ORDER BY revenue DESC;


-- ─────────────────────────────────────────────────────────────────────────
-- 6. Cohort retention triangle (first 6 months since signup)
-- ─────────────────────────────────────────────────────────────────────────
SELECT
    cohort_label,
    cohort_size,
    ROUND(MAX(CASE WHEN months_since_signup = 0 THEN retention_rate END), 2) AS m0,
    ROUND(MAX(CASE WHEN months_since_signup = 1 THEN retention_rate END), 2) AS m1,
    ROUND(MAX(CASE WHEN months_since_signup = 2 THEN retention_rate END), 2) AS m2,
    ROUND(MAX(CASE WHEN months_since_signup = 3 THEN retention_rate END), 2) AS m3,
    ROUND(MAX(CASE WHEN months_since_signup = 6 THEN retention_rate END), 2) AS m6
FROM main_marts.cohort_retention
GROUP BY cohort_label, cohort_size
ORDER BY cohort_label;


-- ─────────────────────────────────────────────────────────────────────────
-- 7. Plan migration economics: MRR, churn and average tenure by plan
-- ─────────────────────────────────────────────────────────────────────────
SELECT
    plan,
    COUNT(*)                                     AS subscriptions,
    ROUND(100.0 * AVG(CASE WHEN is_active THEN 1 ELSE 0 END), 1) AS pct_active,
    ROUND(100.0 * AVG(CASE WHEN is_churned THEN 1 ELSE 0 END), 1) AS pct_churned,
    ROUND(AVG(months_active), 1)                 AS avg_tenure_months,
    ROUND(SUM(CASE WHEN is_active THEN mrr ELSE 0 END)) AS active_mrr
FROM main_marts.fct_subscriptions
GROUP BY plan
ORDER BY active_mrr DESC;


-- ─────────────────────────────────────────────────────────────────────────
-- 8. Regional performance scorecard
-- ─────────────────────────────────────────────────────────────────────────
SELECT
    c.region,
    COUNT(DISTINCT c.customer_id)                AS customers,
    ROUND(SUM(o.recognized_revenue))             AS revenue,
    ROUND(AVG(c.lifetime_revenue))               AS avg_ltv,
    ROUND(100.0 * AVG(CASE WHEN c.has_active_sub THEN 1 ELSE 0 END), 1) AS pct_with_active_sub
FROM main_marts.dim_customers c
LEFT JOIN main_marts.fct_orders o ON c.customer_id = o.customer_id
GROUP BY c.region
ORDER BY revenue DESC;


-- ─────────────────────────────────────────────────────────────────────────
-- 9. Product engagement vs. value: do high-value customers use more features?
-- ─────────────────────────────────────────────────────────────────────────
SELECT
    value_tier,
    COUNT(*)                          AS customers,
    ROUND(AVG(lifetime_events), 0)    AS avg_events,
    ROUND(AVG(lifetime_orders), 1)    AS avg_orders,
    ROUND(AVG(tenure_months), 1)      AS avg_tenure_months,
    ROUND(AVG(recency_days), 0)       AS avg_recency_days
FROM main_marts.customer_segments
GROUP BY value_tier
ORDER BY avg_events DESC;
