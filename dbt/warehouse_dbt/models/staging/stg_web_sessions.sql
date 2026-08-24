-- Typed clickstream sessions for the conversion funnel.
with src as (
    select * from {{ source('raw', 'web_sessions') }}
)
select
    session_id,
    cast(session_ts as timestamp)            as session_ts,
    cast(session_ts as date)                 as session_date,
    date_trunc('month', cast(session_ts as date)) as session_month,
    channel,
    device,
    landing_page,
    cast(pages_viewed as integer)            as pages_viewed,
    cast(duration_sec as integer)            as duration_sec,
    cast(converted as integer)               as converted,
    case when nullif(trim(cast(customer_id as varchar)), '') is null
         then null else cast(customer_id as bigint) end as customer_id
from src
