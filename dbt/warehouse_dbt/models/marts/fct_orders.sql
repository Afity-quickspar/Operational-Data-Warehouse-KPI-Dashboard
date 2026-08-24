-- ============================================================================
-- fct_orders : order-grain fact enriched with customer conformed attributes.
-- ============================================================================
select
    o.order_id,
    o.customer_id,
    o.order_ts,
    o.order_date,
    o.order_month,
    c.region,
    c.plan,
    c.segment_band,
    c.acquisition_channel,
    o.channel                                as order_channel,
    o.gross_amount,
    o.discount_pct,
    o.net_amount,
    o.recognized_revenue,
    o.num_items,
    o.status,
    o.is_recognized
from {{ ref('stg_orders') }} o
left join {{ ref('stg_customers') }} c using (customer_id)
