-- Singular test: daily recognized revenue must reconcile to the order grain
-- within a tiny floating-point tolerance (guards against fan-out joins).
with daily as (
    select sum(recognized_revenue) as rev from {{ ref('kpi_daily') }}
),
orders as (
    select sum(recognized_revenue) as rev from {{ ref('stg_orders') }}
)
select daily.rev as daily_rev, orders.rev as order_rev
from daily cross join orders
where abs(daily.rev - orders.rev) > 1.0
