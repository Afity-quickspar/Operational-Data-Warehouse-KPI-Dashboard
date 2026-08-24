-- Typed product-analytics events (already flattened at ingest).
with src as (
    select * from {{ source('raw', 'events') }}
)
select
    cast(event_id as bigint)                 as event_id,
    cast(customer_id as bigint)              as customer_id,
    event_type,
    cast(event_ts as timestamp)              as event_ts,
    cast(event_ts as date)                   as event_date,
    platform,
    app_version,
    cast(session_len_sec as bigint)          as session_len_sec,
    feature
from src
