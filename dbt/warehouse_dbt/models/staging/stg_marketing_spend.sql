-- Typed monthly paid-media spend (CAC numerator input).
with src as (
    select * from {{ source('raw', 'marketing_spend') }}
)
select
    cast(spend_date as date)                 as spend_date,
    date_trunc('month', cast(spend_date as date)) as spend_month,
    channel,
    region,
    cast(spend as double)                    as spend,
    cast(impressions as bigint)              as impressions,
    cast(clicks as bigint)                   as clicks
from src
