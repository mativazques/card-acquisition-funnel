-- Fact: one row per customer. FKs to dim_date (acq_month), dim_customer, dim_channel;
-- adoption timing and risk flags from the intermediate layer.
-- Grain: customer (customer_id is unique here).
--
-- Attributes (segmento, income_band, age_band, nomprov, canal_entrada) come from
-- int_customer_adoption_resolved, which already aggregates per-customer attributes
-- using MAX to yield one stable value per customer. No secondary join to staging
-- is needed — pulling distinct attributes from staging would create duplicates when
-- a customer's attributes change across snapshot months.

with resolved as (

    select * from {{ ref('int_customer_adoption_resolved') }}

)

select
    customer_id,

    -- foreign keys to dims
    -- acq_date_key is NULL for customers without a parseable fecha_alta (pre-panel)
    case
        when acq_month is not null
        then cast(format_date('%Y%m', acq_month) as int64)
    end                                                      as acq_date_key,

    {{ surrogate_key(['segmento', 'income_band', 'age_band', 'nomprov']) }}
                                                             as customer_key,
    {{ surrogate_key(['canal_entrada']) }}                   as channel_key,

    -- degenerate date attributes (carried for convenience)
    acq_month,
    first_obs_month,
    last_obs_month,
    first_card_month,

    -- cohort / censoring flags
    is_within_panel_cohort,
    is_left_censored_card,
    is_adopted_observed,
    is_adopted_clean,
    is_right_censored,
    has_panel_gaps,

    -- timing
    months_to_adoption,
    n_snapshots_observed,

    -- retention
    retained_1m,
    retained_2m,
    retained_3m,

    -- degenerate segment attributes (for ad-hoc filter; dim key also available)
    segmento,
    income_band,
    age_band

from resolved
