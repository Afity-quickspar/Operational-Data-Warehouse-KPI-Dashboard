-- Singular test: MRR must never be negative.
select subscription_id, mrr
from {{ ref('stg_subscriptions') }}
where mrr < 0
