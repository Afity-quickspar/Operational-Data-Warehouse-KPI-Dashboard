-- ============================================================================
-- dim_date : conformed calendar dimension spanning the data window.
-- Generated with DuckDB's range() so no seed file is required.
-- ============================================================================
with bounds as (
    select
        least(
            (select min(order_date)   from {{ ref('stg_orders') }}),
            (select min(session_date) from {{ ref('stg_web_sessions') }})
        ) as min_d,
        greatest(
            (select max(order_date)   from {{ ref('stg_orders') }}),
            (select max(session_date) from {{ ref('stg_web_sessions') }})
        ) as max_d
),
spine as (
    select unnest(
        range(
            (select min_d from bounds),
            (select max_d from bounds) + interval 1 day,
            interval 1 day
        )
    ) as date_day
)
select
    cast(date_day as date)                    as date_key,
    extract(year   from date_day)             as year,
    extract(quarter from date_day)            as quarter,
    extract(month  from date_day)             as month_num,
    strftime(date_day, '%B')                  as month_name,
    date_trunc('month', date_day)             as month_start,
    extract(week   from date_day)             as week_num,
    extract(dow    from date_day)             as day_of_week,
    strftime(date_day, '%A')                  as day_name,
    (extract(dow from date_day) in (0, 6))    as is_weekend
from spine
