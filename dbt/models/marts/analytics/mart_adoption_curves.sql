-- Adoption vintage curves: cumulative adoption rate by (acquisition cohort x msa).
-- This is the vintage triangle for card adoption — "how does each acquisition cohort's
-- card-adoption rate develop as it ages (months-since-acquisition)?"
--
-- Grain: acq_month x msa.
--   * Restricted to within-panel acquirees (is_within_panel_cohort = true).
--   * Numerator: is_adopted_clean (excludes left-censored customers).
--   * is_cell_right_censored: true if the entire cell cannot be fully observed given
--     the panel end (snapshot_end = 2016-05-01). Computed here so the critic agent
--     reads a field, not re-derives it. Definition:
--       acq_month + msa months > snapshot_end
--     i.e. this cohort did not have enough panel time to complete the msa window.
--   * fully_observed_n: true if is_cell_right_censored = false. Convenience inverse.
--
-- Honesty: only rows where is_cell_right_censored = false represent fully-observed
-- adoption rates. Right-censored cells are included (with the flag set) so the BI layer
-- can choose to plot them as dashed lines or exclude them. The critic agent suppresses
-- right-censored cells from its output by design.

with customers as (

    select
        customer_id,
        acq_month,
        is_within_panel_cohort,
        is_adopted_clean,
        first_card_month,
        months_to_adoption
    from {{ ref('fct_customer') }}
    where is_within_panel_cohort = true

),

-- generate (customer x msa) spine for msa 0..17 (panel spans 17 months)
spine as (

    select
        c.customer_id,
        c.acq_month,
        c.is_adopted_clean,
        c.first_card_month,
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
        msa,
        -- adopted by msa if months_to_adoption <= msa AND adoption is clean
        case
            when is_adopted_clean = true and months_to_adoption <= msa then 1
            else 0
        end                         as adopted_by_msa

    from spine

)

select
    acq_month,
    msa,
    date_add(acq_month, interval msa month)
                                    as as_of_month,

    -- cohort size (stable across msa for a given cohort)
    count(*)                        as n_observed,

    -- cumulative adoption numerator
    sum(adopted_by_msa)             as n_adopted_clean,

    -- cumulative adoption rate (the metric)
    safe_divide(sum(adopted_by_msa), count(*))
                                    as adoption_rate,

    -- right-censoring: the panel ends May 2016 (snapshot_end)
    -- a cell is right-censored if the cohort did not have `msa` full months in the panel
    date_add(acq_month, interval msa month) > date '{{ var("snapshot_end") }}'
                                    as is_cell_right_censored,

    -- convenience inverse
    date_add(acq_month, interval msa month) <= date '{{ var("snapshot_end") }}'
                                    as fully_observed_n

from cumulative
group by acq_month, msa
