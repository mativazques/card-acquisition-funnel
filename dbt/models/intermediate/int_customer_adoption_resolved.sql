-- Resolve customer-level adoption status from the monthly panel.
-- One row per customer. Computes cohort anchor, adoption timing, censoring flags,
-- and retention indicators.
--
-- Key output flags (documented for semantic layer consumers):
--   is_left_censored_card  : customer already held card at first observed snapshot.
--                            Excludes them from is_adopted_clean (0.06% in this panel).
--   is_adopted_clean       : the governed adoption metric numerator. True ONLY if the
--                            0→1 flip was actually observed (not pre-existing).
--   is_right_censored      : acq_month is within 6 months of panel end, so the
--                            msa_6 window is truncated.
--   has_panel_gaps         : TRUE if any expected monthly snapshot is missing between
--                            first and last observation for this customer.
--
-- Retention (retained_1m / 2m / 3m): still holding card at +N months after
-- first_card_month. NULL if not yet adopted; FALSE if adopted but no later
-- snapshot available or card not held at +N.

with monthly as (

    select
        customer_id,
        snapshot_month,
        acq_month,
        card_flag,
        segmento,
        canal_entrada,
        cod_prov,
        nomprov,
        income_band,
        age_band,
        income,
        age
    from {{ ref('stg_customer_month') }}

),

-- step 1: per-customer panel summaries (no correlated subqueries)
customer_panel as (

    select
        customer_id,
        max(acq_month)                      as acq_month,
        min(snapshot_month)                 as first_obs_month,
        max(snapshot_month)                 as last_obs_month,
        count(snapshot_month)               as n_snapshots_observed,
        min(case when card_flag = 1 then snapshot_month end)
                                            as first_card_month,
        -- attributes: use MAX to pick a stable non-null value across rows
        max(segmento)                       as segmento,
        max(canal_entrada)                  as canal_entrada,
        max(cod_prov)                       as cod_prov,
        max(nomprov)                        as nomprov,
        max(income_band)                    as income_band,
        max(age_band)                       as age_band,
        max(income)                         as income_max,
        max(age)                            as age_max

    from monthly
    group by customer_id

),

-- step 2: look up card_flag at first_obs_month via a join (avoids correlated subquery)
with_first_obs_card as (

    select
        cp.*,
        coalesce(m.card_flag, 0)            as card_at_first_obs
    from customer_panel cp
    left join monthly m
        on  m.customer_id    = cp.customer_id
        and m.snapshot_month = cp.first_obs_month

),

-- step 3: detect panel gaps
-- Expected monthly snapshots between first and last obs = date_diff + 1
-- A customer has gaps if n_snapshots_observed < expected span.
with_gaps as (

    select
        *,
        date_diff(last_obs_month, first_obs_month, month) + 1
            as expected_snapshots,
        n_snapshots_observed
            < (date_diff(last_obs_month, first_obs_month, month) + 1)
            as has_panel_gaps

    from with_first_obs_card

),

-- step 4: retention checks via left joins to the monthly panel
retention_checks as (

    select
        w.customer_id,
        w.acq_month,
        w.first_obs_month,
        w.last_obs_month,
        w.first_card_month,
        w.card_at_first_obs,
        w.n_snapshots_observed,
        w.expected_snapshots,
        w.has_panel_gaps,
        w.segmento,
        w.canal_entrada,
        w.cod_prov,
        w.nomprov,
        w.income_band,
        w.age_band,
        w.income_max,
        w.age_max,

        -- still holding at +1/+2/+3 months after first_card_month
        coalesce(m1.card_flag, 0)           as card_at_1m,
        coalesce(m2.card_flag, 0)           as card_at_2m,
        coalesce(m3.card_flag, 0)           as card_at_3m

    from with_gaps w
    left join monthly m1
        on  m1.customer_id    = w.customer_id
        and w.first_card_month is not null
        and m1.snapshot_month = date_add(w.first_card_month, interval 1 month)
    left join monthly m2
        on  m2.customer_id    = w.customer_id
        and w.first_card_month is not null
        and m2.snapshot_month = date_add(w.first_card_month, interval 2 month)
    left join monthly m3
        on  m3.customer_id    = w.customer_id
        and w.first_card_month is not null
        and m3.snapshot_month = date_add(w.first_card_month, interval 3 month)

),

-- step 5: build the final resolved flags
final as (

    select
        customer_id,
        acq_month,
        first_obs_month,
        last_obs_month,
        n_snapshots_observed,
        has_panel_gaps,

        -- within-panel cohort: acq_month falls inside the 17-month panel window
        (acq_month is not null
         and acq_month >= date '2015-01-01'
         and acq_month <= date '2016-05-01')
            as is_within_panel_cohort,

        first_card_month,

        -- left-censoring: card held at very first observed snapshot
        -- (we never saw the 0→1 flip; pre-existing holding, not observed adoption)
        (card_at_first_obs = 1
         and first_card_month is not null
         and first_card_month = first_obs_month)
            as is_left_censored_card,

        -- was the 0→1 flip actually observed in the panel?
        -- Observed if: card was ever held AND the flip happened AFTER first_obs_month
        (first_card_month is not null
         and first_card_month > first_obs_month)
            as is_adopted_observed,

        -- clean adoption: observed flip AND not left-censored
        -- This is the numerator for adoption_rate in the semantic layer.
        (first_card_month is not null
         and first_card_month > first_obs_month
         and not (card_at_first_obs = 1
                  and first_card_month = first_obs_month))
            as is_adopted_clean,

        -- months-to-adoption from acq_month to first observed card month
        case
            when first_card_month is not null
             and acq_month is not null
             and first_card_month > first_obs_month  -- exclude left-censored
            then date_diff(first_card_month, acq_month, month)
        end                                 as months_to_adoption,

        -- right-censoring: acquired within 6 months of panel end
        -- such customers may not have had enough panel time to adopt at msa_6
        case
            when acq_month is null then null
            else acq_month > date_add(date '{{ var("snapshot_end") }}', interval -6 month)
        end                                 as is_right_censored,

        -- retention flags (NULL if not adopted)
        case
            when first_card_month is not null
             and first_card_month > first_obs_month  -- clean adopters only
            then (card_at_1m = 1)
        end                                 as retained_1m,

        case
            when first_card_month is not null
             and first_card_month > first_obs_month
            then (card_at_2m = 1)
        end                                 as retained_2m,

        case
            when first_card_month is not null
             and first_card_month > first_obs_month
            then (card_at_3m = 1)
        end                                 as retained_3m,

        -- attributes for downstream dims / grouping
        segmento,
        canal_entrada,
        cod_prov,
        nomprov,
        income_band,
        age_band,
        income_max,
        age_max

    from retention_checks

)

select * from final
