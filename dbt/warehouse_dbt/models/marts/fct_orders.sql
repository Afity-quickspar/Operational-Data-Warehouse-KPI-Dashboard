-- ============================================================================
-- fct_orders : order-grain fact enriched with customer conformed attributes.
-- Incremental: at production scale, orders arrive daily and this fact grows
-- without bound, so each run only processes rows newer than what's already
-- loaded rather than rebuilding the full table. `dbt run --full-refresh`
-- (or a change to `stg_orders`/`stg_customers`) rebuilds it from scratch.
-- ============================================================================
{{
    config(
        materialized='incremental',
        unique_key='order_id',
        incremental_strategy='delete+insert',
        on_schema_change='sync_all_columns'
    )
}}

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

{% if is_incremental() %}
where o.order_ts > (select coalesce(max(order_ts), '1900-01-01'::timestamp) from {{ this }})
{% endif %}
