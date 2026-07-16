-- Customer dimension. NOTE: Santander obfuscates `ncodpers` (numeric codes,
-- no stable cross-dataset identity) and does not expose a stable person key
-- in this public release. This is therefore a JUNK DIMENSION of applicant
-- attribute combinations, not a per-person dimension — honest by design.
-- (Same design rationale as dim_borrower in flagship #1 credit-risk-cockpit.)
--
-- Attributes are sourced from int_customer_adoption_resolved, which has already
-- aggregated per-customer attributes using MAX (one stable value per customer).
-- This guarantees that the surrogate key computed here matches the one computed
-- in fct_customer — both use the same resolved attribute values.
--
-- Grain: one row per distinct combination of (segmento, income_band, age_band, province).

with resolved as (

    select distinct
        segmento,
        income_band,
        age_band,
        nomprov
    from {{ ref('int_customer_adoption_resolved') }}

)

select
    {{ surrogate_key(['segmento', 'income_band', 'age_band', 'nomprov']) }}
        as customer_key,
    segmento,
    income_band,
    age_band,
    nomprov                                         as province
from resolved
