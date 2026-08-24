-- Singular test: recognized revenue must never be negative.
select order_id, net_amount
from {{ ref('stg_orders') }}
where net_amount < 0
