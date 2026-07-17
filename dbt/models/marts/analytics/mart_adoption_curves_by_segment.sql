-- Adoption vintage curves BY SEGMENT: cumulative card-adoption rate by
-- (acquisition cohort x segmento x msa). Same construction as mart_adoption_curves
-- but retaining the segment grain, so the semantic layer can hold segment mix constant
-- when computing adoption_rate_segment_adjusted (the D14 mix-decomposition metric).
--
-- Grain: acq_month x segmento x msa.
--   * Restricted to within-panel acquirees (is_within_panel_cohort = true).
--   * Numerator: is_adopted_clean (excludes left-censored customers).
--   * is_cell_right_censored: acq_month + msa months > snapshot_end (2016-05-01) — the
--     cohort did not have enough panel time to complete the msa window. Computed here so
--     the semantic layer / critic reads a field rather than re-deriving it.
--
-- Honesty: only rows with is_cell_right_censored = false are fully-observed adoption
-- rates. The segment-adjusted metric consumes only those cells.

with customers as (

    select
        customer_id,
        acq_month,
        coalesce(segmento, 'unknown')   as segmento,
        is_within_panel_cohort,
        is_adopted_clean,
        months_to_adoption
    from {{ ref('fct_customer') }}
    where is_within_panel_cohort = true

),

-- generate (customer x msa) spine for msa 0..17 (panel spans 17 months)
spine as (

    select
        c.customer_id,
        c.acq_month,
        c.segmento,
        c.is_adopted_clean,
        c.months_to_adoption,
        msa
    from customers c,
         unnest(generate_array(0, 17)) as msa

),

-- for each (customer x msa), has the customer adopted by this msa?
cumulative as (

    select
        customer_id,
        acq_month,
        segmento,
        msa,
        case
            when is_adopted_clean = true and months_to_adoption <= msa then 1
            else 0
        end                             as adopted_by_msa

    from spine

)

select
    acq_month,
    segmento,
    msa,
    date_add(acq_month, interval msa month)
                                        as as_of_month,

    -- cohort x segment size (stable across msa for a given cell)
    count(*)                            as n_observed,

    -- cumulative adoption numerator
    sum(adopted_by_msa)                 as n_adopted_clean,

    -- cumulative adoption rate (the metric, per segment)
    safe_divide(sum(adopted_by_msa), count(*))
                                        as adoption_rate,

    -- right-censoring: the panel ends May 2016 (snapshot_end)
    date_add(acq_month, interval msa month) > date '{{ var("snapshot_end") }}'
                                        as is_cell_right_censored,

    -- convenience inverse
    date_add(acq_month, interval msa month) <= date '{{ var("snapshot_end") }}'
                                        as fully_observed_n

from cumulative
group by acq_month, segmento, msa
