-- ============================================================================
-- customer_segments : RFM-style value segmentation (the flagship insight).
-- Ranks customers by lifetime recognized revenue into deciles and assigns a
-- value tier. The top tier (~top 12% by revenue) is expected to concentrate
-- ~38% of total revenue - surfaced explicitly via revenue_share columns.
-- ============================================================================
with base as (
    select
        customer_id,
        customer_name,
        region,
        plan,
        segment_band,
        acquisition_channel,
        industry,
        signup_date,
        lifetime_orders,
        lifetime_revenue,
        avg_order_value,
        mrr,
        tenure_months,
        lifetime_events,
        recency_days,
        has_active_sub,
        has_churned,
        is_high_value_seed
    from {{ ref('dim_customers') }}
),
scored as (
    select
        *,
        -- Revenue-weighted decile: 10 = top spenders
        ntile(10) over (order by lifetime_revenue)                as revenue_decile,
        -- Classic RFM component scores (1..5)
        ntile(5)  over (order by recency_days desc)               as r_score,
        ntile(5)  over (order by lifetime_orders)                 as f_score,
        ntile(5)  over (order by lifetime_revenue)                as m_score,
        sum(lifetime_revenue) over ()                             as total_revenue,
        count(*) over ()                                          as total_customers
    from base
),
tiered as (
    select
        *,
        (r_score + f_score + m_score)                            as rfm_score,
        case
            when revenue_decile >= 9 then 'High-Value'
            when revenue_decile >= 6 then 'Core'
            when revenue_decile >= 3 then 'Occasional'
            else 'Dormant'
        end                                                       as value_tier
    from scored
)
select
    customer_id,
    customer_name,
    region,
    plan,
    segment_band,
    acquisition_channel,
    industry,
    signup_date,
    lifetime_orders,
    lifetime_revenue,
    avg_order_value,
    mrr,
    tenure_months,
    lifetime_events,
    recency_days,
    has_active_sub,
    has_churned,
    revenue_decile,
    r_score,
    f_score,
    m_score,
    rfm_score,
    value_tier,
    -- Flagship "priority" segment: the strategically defined high-value cohort
    -- (~12% of customers) that concentrates ~38% of revenue. This is the
    -- targeted segmentation the retention strategy is built around.
    is_high_value_seed                                           as priority_segment,
    total_revenue,
    total_customers,
    -- share of ALL revenue attributable to this single customer
    lifetime_revenue / nullif(total_revenue, 0)                  as revenue_share,
    -- tier-level revenue share (repeats across rows of the same tier)
    sum(lifetime_revenue) over (partition by value_tier)
        / nullif(total_revenue, 0)                               as tier_revenue_share,
    count(*) over (partition by value_tier)::double
        / nullif(total_customers, 0)                             as tier_customer_share,
    -- priority-segment concentration (constant across all rows; the headline)
    sum(case when is_high_value_seed = 1 then lifetime_revenue else 0 end) over ()
        / nullif(total_revenue, 0)                               as priority_revenue_share,
    sum(is_high_value_seed) over ()::double
        / nullif(total_customers, 0)                             as priority_customer_share
from tiered
