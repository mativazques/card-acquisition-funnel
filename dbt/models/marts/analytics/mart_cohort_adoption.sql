-- Cohort adoption summary: one row per (acq_month x segmento) with adoption,
-- retention, and time-to-adoption metrics. Cohort heatmap source; semantic layer
-- entry point for the proactive digest.
--
-- Grain: acq_month x segmento.
-- Restricted to within-panel acquirees (is_within_panel_cohort = true).
--
-- Honesty: fully_observed_6 / fully_observed_12 tell the consumer whether the
-- cohort was still acquiring customers at the point where the panel can fully
-- observe 6 or 12 months of post-acquisition behavior.
-- n_right_censored counts customers for whom even the msa_6 window was truncated.
--
-- Right-censoring definition (from BLUEPRINT.md D9):
--   fully_observed_6  = true if acq_month + 6 months <= 2016-05-01
--   fully_observed_12 = true if acq_month + 12 months <= 2016-05-01

with customers as (

    select
        customer_id,
        acq_month,
        segmento,
        is_within_panel_cohort,
        is_adopted_clean,
        is_right_censored,
        has_panel_gaps,
        months_to_adoption,
        retained_1m,
        retained_2m,
        retained_3m
    from {{ ref('fct_customer') }}
    where is_within_panel_cohort = true

)

select
    acq_month,
    coalesce(segmento, 'unknown')   as segmento,

    -- cohort size
    count(*)                        as cohort_size,

    -- adoption metrics
    sum(case when is_adopted_clean then 1 else 0 end)
                                    as n_adopted,
    safe_divide(
        sum(case when is_adopted_clean then 1 else 0 end),
        count(*)
    )                               as adoption_rate,

    -- right-censoring counts (within this cohort x segment cell)
    sum(case when is_right_censored then 1 else 0 end)
                                    as n_right_censored,

    -- fully-observed flags for this cohort at each window
    -- (true if the WHOLE cohort has had enough panel time)
    logical_and(
        date_add(acq_month, interval 6 month) <= date '{{ var("snapshot_end") }}'
    )                               as fully_observed_6,
    logical_and(
        date_add(acq_month, interval 12 month) <= date '{{ var("snapshot_end") }}'
    )                               as fully_observed_12,

    -- time-to-adoption (among clean-adopted only)
    avg(case when is_adopted_clean then months_to_adoption end)
                                    as avg_months_to_adoption,
    min(case when is_adopted_clean then months_to_adoption end)
                                    as min_months_to_adoption,
    max(case when is_adopted_clean then months_to_adoption end)
                                    as max_months_to_adoption,

    -- retention (among all customers; NULL if not adopted)
    safe_divide(
        sum(case when retained_1m = true then 1 else 0 end),
        sum(case when is_adopted_clean then 1 else 0 end)
    )                               as retention_rate_1m,
    safe_divide(
        sum(case when retained_2m = true then 1 else 0 end),
        sum(case when is_adopted_clean then 1 else 0 end)
    )                               as retention_rate_2m,
    safe_divide(
        sum(case when retained_3m = true then 1 else 0 end),
        sum(case when is_adopted_clean then 1 else 0 end)
    )                               as retention_rate_3m,

    -- panel quality flag: share of customers with panel gaps
    safe_divide(
        sum(case when has_panel_gaps then 1 else 0 end),
        count(*)
    )                               as share_with_panel_gaps

from customers
group by acq_month, segmento
