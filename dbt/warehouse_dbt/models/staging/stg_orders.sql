-- Typed order fact with derived revenue flags.
with src as (
    select * from {{ source('raw', 'orders') }}
)
select
    cast(order_id as bigint)                 as order_id,
    cast(customer_id as bigint)              as customer_id,
    cast(order_ts as timestamp)              as order_ts,
    cast(order_ts as date)                   as order_date,
    date_trunc('month', cast(order_ts as date)) as order_month,
    cast(gross_amount as double)             as gross_amount,
    cast(discount_pct as double)             as discount_pct,
    cast(net_amount as double)               as net_amount,
    cast(num_items as integer)               as num_items,
    channel,
    status,
    case when status = 'completed' then net_amount else 0 end as recognized_revenue,
    (status = 'completed')                   as is_recognized
from src
