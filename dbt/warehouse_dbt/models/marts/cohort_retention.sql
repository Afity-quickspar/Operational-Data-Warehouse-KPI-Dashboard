-- ============================================================================
-- cohort_retention : monthly signup cohorts x months-since-signup retention.
-- Retention = share of a cohort with product activity (order OR event) in the
-- Nth month after signup. Powers the retention heatmap / curve in BI tools.
-- ============================================================================
with cohorts as (
    select
        customer_id,
        date_trunc('month', signup_date) as cohort_month
    from {{ ref('stg_customers') }}
),
activity as (
    -- product-usage retention -> events are the activity signal
    select distinct customer_id, date_trunc('month', event_date) as active_month
    from {{ ref('stg_events') }}
),
joined as (
    select
        c.cohort_month,
        c.customer_id,
        date_diff('month', c.cohort_month, a.active_month) as months_since_signup
    from cohorts c
    join activity a on c.customer_id = a.customer_id
    where a.active_month >= c.cohort_month
),
cohort_sizes as (
    select cohort_month, count(distinct customer_id) as cohort_size
    from cohorts group by 1
),
retained as (
    select
        cohort_month,
        months_since_signup,
        count(distinct customer_id) as active_customers
    from joined
    where months_since_signup between 0 and 12
    group by 1, 2
)
select
    r.cohort_month,
    strftime(r.cohort_month, '%Y-%m')                     as cohort_label,
    r.months_since_signup,
    cs.cohort_size,
    r.active_customers,
    r.active_customers::double / nullif(cs.cohort_size, 0) as retention_rate
from retained r
join cohort_sizes cs on r.cohort_month = cs.cohort_month
order by r.cohort_month, r.months_since_signup
