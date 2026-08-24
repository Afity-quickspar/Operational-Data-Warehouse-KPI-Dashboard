-- ============================================================================
-- fct_subscriptions : subscription-grain fact with plan economics.
-- ============================================================================
select
    s.subscription_id,
    s.customer_id,
    c.region,
    c.acquisition_channel,
    c.segment_band,
    s.plan,
    s.mrr,
    s.mrr * 12                               as arr,
    s.start_date,
    date_trunc('month', s.start_date)        as cohort_month,
    s.status,
    s.churn_date,
    s.months_active,
    s.billing_interval,
    s.is_churned,
    s.is_active
from {{ ref('stg_subscriptions') }} s
left join {{ ref('stg_customers') }} c using (customer_id)
