{{ config(
    materialized='table',
    partition_by={
        "field": "snapshot_month",
        "data_type": "date",
        "granularity": "month"
    },
    cluster_by=["acq_month", "segmento"]
) }}

-- Fact: one row per customer x snapshot month (the monthly panel).
-- Materialized as a TABLE (not a VIEW) — ~13M rows. A VIEW would impose
-- 3–8 s full-scan latency on every Streamlit/semantic-layer call.
-- Storage ~1–2 GB, within BigQuery's 10 GB/mo free tier.
-- (This overrides the VIEW pattern from flagship #1's fct_loan_month which
-- is only ~2.2M rows — the VIEW pattern does NOT transfer here.)
--
-- months-since-acquisition (msa): panel-observed months since acq_month.
-- Computed as date_diff(snapshot_month, acq_month, month).
-- NULL for customers where acq_month is NULL (pre-panel acquirees without
-- a parseable fecha_alta).

with monthly as (

    select
        customer_id,
        snapshot_month,
        acq_month,
        card_flag,
        segmento,
        canal_entrada,
        income_band,
        age_band,
        nomprov
    from {{ ref('stg_customer_month') }}

),

resolved as (

    select
        customer_id,
        acq_month,
        is_within_panel_cohort,
        is_adopted_clean,
        is_right_censored,
        first_card_month,
        has_panel_gaps
    from {{ ref('int_customer_adoption_resolved') }}

)

select
    -- surrogate key for the row
    {{ surrogate_key(['m.customer_id', 'm.snapshot_month']) }}  as customer_month_key,

    m.customer_id,
    m.snapshot_month,
    m.acq_month,

    -- months-since-acquisition: months elapsed from cohort month to this snapshot
    -- NULL if acq_month is NULL (customer without a parseable acquisition date)
    case
        when m.acq_month is not null
        then date_diff(m.snapshot_month, m.acq_month, month)
    end                                             as msa,

    m.card_flag,
    m.segmento,
    m.canal_entrada,
    m.income_band,
    m.age_band,
    m.nomprov,

    -- carried from resolved for convenience
    r.is_within_panel_cohort,
    r.is_adopted_clean,
    r.is_right_censored,
    r.has_panel_gaps

from monthly m
left join resolved r using (customer_id)
