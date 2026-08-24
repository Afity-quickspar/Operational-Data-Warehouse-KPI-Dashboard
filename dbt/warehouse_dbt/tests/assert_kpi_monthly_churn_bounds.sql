-- Singular test: monthly churn rate must be a valid probability in [0, 1].
select month, churn_rate
from {{ ref('kpi_monthly') }}
where churn_rate < 0 or churn_rate > 1
