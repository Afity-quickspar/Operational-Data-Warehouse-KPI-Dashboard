-- Typed subscription fact with churn flags.
with src as (
    select * from {{ source('raw', 'subscriptions') }}
)
select
    cast(subscription_id as bigint)          as subscription_id,
    cast(customer_id as bigint)              as customer_id,
    plan,
    cast(mrr as double)                      as mrr,
    cast(start_date as date)                 as start_date,
    status,
    -- churn_date is auto-typed DATE by the CSV reader (blanks -> NULL)
    try_cast(churn_date as date)             as churn_date,
    cast(months_active as integer)           as months_active,
    billing_interval,
    (status = 'churned')                     as is_churned,
    (status = 'active')                      as is_active
from src
