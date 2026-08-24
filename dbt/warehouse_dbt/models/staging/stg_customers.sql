-- Cleansed, typed customer dimension source.
with src as (
    select * from {{ source('raw', 'customers') }}
)
select
    cast(customer_id as bigint)              as customer_id,
    trim(customer_name)                      as customer_name,
    nullif(trim(email), '')                  as email,
    cast(signup_date as date)                as signup_date,
    region,
    country,
    acquisition_channel,
    plan,
    cast(company_size as integer)            as company_size,
    industry,
    cast(is_high_value_seed as integer)      as is_high_value_seed,
    case
        when company_size >= 500 then 'Enterprise'
        when company_size >= 100 then 'Mid-Market'
        else 'SMB'
    end                                      as segment_band
from src
