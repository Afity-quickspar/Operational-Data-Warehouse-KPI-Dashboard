-- ============================================================================
-- dim_customers : enriched customer dimension.
-- Joins CRM attributes to lifetime revenue, order behaviour and subscription
-- state so downstream marts and BI tools have a single wide customer record.
-- ============================================================================
with c as (
    select * from {{ ref('stg_customers') }}
),
order_rollup as (
    select
        customer_id,
        count(*)                                          as lifetime_orders,
        sum(recognized_revenue)                           as lifetime_revenue,
        avg(case when is_recognized then net_amount end)  as avg_order_value,
        min(order_date)                                   as first_order_date,
        max(order_date)                                   as last_order_date
    from {{ ref('stg_orders') }}
    group by 1
),
sub as (
    select
        customer_id,
        max(mrr)          as mrr,
        bool_or(is_active) as has_active_sub,
        bool_or(is_churned) as has_churned,
        max(months_active) as months_active
    from {{ ref('stg_subscriptions') }}
    group by 1
),
engagement as (
    select customer_id, count(*) as lifetime_events
    from {{ ref('stg_events') }}
    group by 1
)
select
    c.customer_id,
    c.customer_name,
    c.email,
    c.signup_date,
    c.region,
    c.country,
    c.acquisition_channel,
    c.plan,
    c.company_size,
    c.segment_band,
    c.industry,
    c.is_high_value_seed,
    coalesce(o.lifetime_orders, 0)          as lifetime_orders,
    coalesce(o.lifetime_revenue, 0)         as lifetime_revenue,
    coalesce(o.avg_order_value, 0)          as avg_order_value,
    o.first_order_date,
    o.last_order_date,
    coalesce(s.mrr, 0)                       as mrr,
    coalesce(s.has_active_sub, false)       as has_active_sub,
    coalesce(s.has_churned, false)          as has_churned,
    coalesce(s.months_active, 0)            as tenure_months,
    coalesce(e.lifetime_events, 0)          as lifetime_events,
    -- simple recency in days as of the latest order in the warehouse
    date_diff(
        'day', o.last_order_date,
        (select max(last_order_date) from order_rollup)
    )                                        as recency_days
from c
left join order_rollup o on c.customer_id = o.customer_id
left join sub s          on c.customer_id = s.customer_id
left join engagement e   on c.customer_id = e.customer_id
