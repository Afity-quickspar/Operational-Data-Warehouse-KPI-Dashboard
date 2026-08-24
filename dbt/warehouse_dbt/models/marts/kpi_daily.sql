-- ============================================================================
-- kpi_daily : one row per calendar day with the core operational metrics.
-- Feeds trend lines and the daily-refresh tiles in Power BI / Streamlit.
-- ============================================================================
with orders as (
    select
        order_date,
        sum(recognized_revenue)                      as recognized_revenue,
        count(*)                                      as total_orders,
        count(*) filter (where is_recognized)         as completed_orders,
        count(*) filter (where status = 'refunded')   as refunded_orders,
        count(distinct customer_id)                   as ordering_customers,
        avg(case when is_recognized then net_amount end) as avg_order_value
    from {{ ref('stg_orders') }}
    group by 1
),
signups as (
    select signup_date as d, count(*) as new_customers
    from {{ ref('stg_customers') }}
    group by 1
),
sessions as (
    select
        session_date as d,
        count(*)                        as sessions,
        sum(converted)                  as conversions
    from {{ ref('stg_web_sessions') }}
    group by 1
),
events as (
    select event_date as d, count(*) as events
    from {{ ref('stg_events') }}
    group by 1
)
select
    d.date_key,
    d.year,
    d.quarter,
    d.month_name,
    d.day_name,
    d.is_weekend,
    coalesce(o.recognized_revenue, 0)   as recognized_revenue,
    coalesce(o.total_orders, 0)         as total_orders,
    coalesce(o.completed_orders, 0)     as completed_orders,
    coalesce(o.refunded_orders, 0)      as refunded_orders,
    coalesce(o.ordering_customers, 0)   as ordering_customers,
    coalesce(o.avg_order_value, 0)      as avg_order_value,
    coalesce(su.new_customers, 0)       as new_customers,
    coalesce(se.sessions, 0)            as sessions,
    coalesce(se.conversions, 0)         as conversions,
    case when coalesce(se.sessions, 0) > 0
         then se.conversions::double / se.sessions else 0 end as conversion_rate,
    coalesce(ev.events, 0)              as product_events
from {{ ref('dim_date') }} d
left join orders   o  on d.date_key = o.order_date
left join signups  su on d.date_key = su.d
left join sessions se on d.date_key = se.d
left join events   ev on d.date_key = ev.d
