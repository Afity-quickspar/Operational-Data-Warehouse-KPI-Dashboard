-- ============================================================================
-- kpi_monthly : the executive KPI mart.
-- One row per month with all SIX headline KPIs:
--   1. Revenue (recognized)      4. LTV (ARPA / churn)
--   2. Churn rate                5. Conversion rate
--   3. CAC                       6. 30-day retention (cohort-anchored)
-- Plus supporting measures (MRR, ARPA, new/active customers, refund rate).
-- ============================================================================
with month_spine as (
    select distinct month_start as month
    from {{ ref('dim_date') }}
    where month_start <= (select max(order_month) from {{ ref('stg_orders') }})
),

-- 1. Revenue -----------------------------------------------------------------
revenue as (
    select
        order_month as month,
        sum(recognized_revenue)                          as recognized_revenue,
        count(*) filter (where is_recognized)            as completed_orders,
        count(*) filter (where status = 'refunded')      as refunded_orders,
        count(distinct customer_id) filter (where is_recognized) as paying_customers,
        avg(case when is_recognized then net_amount end) as avg_order_value
    from {{ ref('stg_orders') }}
    group by 1
),

-- New customers by signup month ----------------------------------------------
new_cust as (
    select date_trunc('month', signup_date) as month, count(*) as new_customers
    from {{ ref('stg_customers') }}
    group by 1
),

-- 2. Churn : churned subs in month / active subs at start of month -----------
sub_base as (
    select customer_id, mrr, start_date, churn_date,
           date_trunc('month', start_date) as start_month,
           date_trunc('month', churn_date) as churn_month
    from {{ ref('stg_subscriptions') }}
),
churn as (
    select
        m.month,
        count(*) filter (
            where s.start_date < m.month
              and (s.churn_date is null or s.churn_date >= m.month)
        )                                                as active_at_start,
        count(*) filter (where s.churn_month = m.month)  as churned_in_month
    from month_spine m
    left join sub_base s on true
    group by 1
),

-- MRR outstanding at month end -----------------------------------------------
mrr as (
    select
        m.month,
        sum(s.mrr) filter (
            where s.start_date <= m.month
              and (s.churn_date is null or s.churn_date > m.month)
        )                                                as active_mrr,
        count(*) filter (
            where s.start_date <= m.month
              and (s.churn_date is null or s.churn_date > m.month)
        )                                                as active_customers
    from month_spine m
    left join sub_base s on true
    group by 1
),

-- 3. CAC : paid spend in month / new customers acquired ----------------------
spend as (
    select spend_month as month, sum(spend) as marketing_spend
    from {{ ref('stg_marketing_spend') }}
    group by 1
),

-- 5. Conversion : converted sessions / total sessions ------------------------
conv as (
    select
        session_month as month,
        count(*)            as sessions,
        sum(converted)      as conversions
    from {{ ref('stg_web_sessions') }}
    group by 1
),

-- 6. 30-day retention (cohort-anchored, fixed return window) -----------------
-- Of customers who signed up in month M, the share with any order OR event in
-- the [signup+30, signup+60) day window -> a genuine "did they come back in
-- their second month" retention signal (not a saturating ever-active flag).
-- Cohorts whose 60-day window has not fully elapsed are excluded downstream.
cohort_activity as (
    select
        c.customer_id,
        date_trunc('month', c.signup_date) as cohort_month,
        c.signup_date,
        -- retention is a PRODUCT-USAGE signal -> events only, not orders
        max(case when e.event_date >= c.signup_date + 30
                  and e.event_date <  c.signup_date + 60 then 1 else 0 end) as retained_event
    from {{ ref('stg_customers') }} c
    left join {{ ref('stg_events') }} e on c.customer_id = e.customer_id
    group by 1, 2, 3
),
data_max as (
    select max(event_date) as max_activity_date from {{ ref('stg_events') }}
),
retention as (
    select
        cohort_month as month,
        count(*)                                                       as cohort_size,
        sum(retained_event)                                            as retained_30d,
        -- flag cohorts that are old enough for the 60-day window to have closed
        bool_and(signup_date + 60 <= (select max_activity_date from data_max)) as is_mature
    from cohort_activity
    group by 1
)

select
    m.month,
    extract(year from m.month)                        as year,
    strftime(m.month, '%Y-%m')                         as month_label,

    -- 1. Revenue
    coalesce(r.recognized_revenue, 0)                 as recognized_revenue,
    coalesce(r.completed_orders, 0)                   as completed_orders,
    coalesce(r.refunded_orders, 0)                    as refunded_orders,
    case when coalesce(r.completed_orders,0) + coalesce(r.refunded_orders,0) > 0
         then r.refunded_orders::double
              / (r.completed_orders + r.refunded_orders) else 0 end as refund_rate,
    coalesce(r.avg_order_value, 0)                    as avg_order_value,
    coalesce(nc.new_customers, 0)                     as new_customers,

    -- MRR / ARPA
    coalesce(mr.active_mrr, 0)                         as active_mrr,
    coalesce(mr.active_customers, 0)                   as active_customers,
    case when coalesce(mr.active_customers,0) > 0
         then r.recognized_revenue / mr.active_customers else 0 end as arpa,

    -- 2. Churn
    coalesce(ch.churned_in_month, 0)                  as churned_customers,
    coalesce(ch.active_at_start, 0)                   as active_at_start,
    case when coalesce(ch.active_at_start,0) > 0
         then ch.churned_in_month::double / ch.active_at_start else 0 end as churn_rate,

    -- 3. CAC
    coalesce(sp.marketing_spend, 0)                   as marketing_spend,
    case when coalesce(nc.new_customers,0) > 0
         then sp.marketing_spend / nc.new_customers else 0 end as cac,

    -- 4. LTV = ARPA / churn_rate  (guarded)
    case
        when coalesce(mr.active_customers,0) > 0
             and coalesce(ch.active_at_start,0) > 0
             and ch.churned_in_month > 0
        then (r.recognized_revenue / mr.active_customers)
             / (ch.churned_in_month::double / ch.active_at_start)
        else 0
    end                                               as ltv,

    -- 5. Conversion
    coalesce(cv.sessions, 0)                           as sessions,
    coalesce(cv.conversions, 0)                        as conversions,
    case when coalesce(cv.sessions,0) > 0
         then cv.conversions::double / cv.sessions else 0 end as conversion_rate,

    -- 6. 30-day retention
    coalesce(rt.cohort_size, 0)                        as cohort_size,
    coalesce(rt.retained_30d, 0)                       as retained_30d,
    coalesce(rt.is_mature, false)                      as cohort_is_mature,
    case when coalesce(rt.cohort_size,0) > 0
         then rt.retained_30d::double / rt.cohort_size else 0 end as retention_30d

from month_spine m
left join revenue   r  on m.month = r.month
left join new_cust  nc on m.month = nc.month
left join churn     ch on m.month = ch.month
left join mrr       mr on m.month = mr.month
left join spend     sp on m.month = sp.month
left join conv      cv on m.month = cv.month
left join retention rt on m.month = rt.month
order by m.month
