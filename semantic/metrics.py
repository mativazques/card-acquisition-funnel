"""The governed metric registry — the single source of truth.

Each metric is defined ONCE here (definition, unit, valid windows, honesty caveats, and
the SQL that computes it over the marts). BI, the reactive copilot, and the proactive
ADK digest all read this registry, so a metric means exactly the same thing everywhere.
Every scalar metric's SQL returns rows of `(cohort, value)` where `cohort` is the
acquisition month formatted `YYYY-MM`. Compositional metrics (segment_mix) return rows of
`(cohort, dimension, share)` instead and are flagged `compositional=True`.

The mix-decomposition pair — `segment_mix` and `adoption_rate_segment_adjusted` — is
first-class, not a footnote: the lead finding (D14) is that the ~7x drop in the blended
adoption rate across 2015 is mostly acquisition-mix drift (from ~85% PARTICULARES to ~76%
UNIVERSITARIO), not a change in the card offer. `adoption_rate_segment_adjusted` holds the
segment mix constant so a mix shift cannot masquerade as a genuine adoption change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .windows import WINDOW_MSA, WINDOW_RETENTION_COL, Window

# Mart names; the caller supplies a resolver that fully-qualifies them.
COHORT = "mart_cohort_adoption"            # acq_month x segmento summary
CURVES = "mart_adoption_curves"            # acq_month x msa vintage triangle
CURVES_SEG = "mart_adoption_curves_by_segment"  # acq_month x segmento x msa
CUSTOMER = "fct_customer"                  # one row per customer

MartTable = Callable[[str], str]  # name -> `project.dataset.name`


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    description: str
    unit: str  # "rate" | "count" | "ratio" | "composition"
    valid_windows: tuple[Window, ...]
    build_sql: Callable[[Window, MartTable], str]
    caveats: tuple[str, ...] = ()
    compositional: bool = False
    # Optional per-segment breakdown (D17): returns rows of (cohort, segment, value, n).
    # Only metrics with a real cohort x segmento x msa grain expose this — the by-segment
    # analyst slice and the critic's min-n guard consume the per-cell value AND n.
    build_segment_sql: Callable[[Window, MartTable], str] | None = None

    def supports(self, window: Window) -> bool:
        return window in self.valid_windows


# --- SQL builders (one per metric) -------------------------------------------------
# All scalar builders return columns (cohort, value). `cohort` = format_date('%Y-%m').

def _cohort_size_sql(_w: Window, mt: MartTable) -> str:
    return f"""
        select format_date('%Y-%m', acq_month) as cohort,
               sum(cohort_size) as value
        from {mt(COHORT)}
        group by acq_month
    """


def _adoption_rate_sql(w: Window, mt: MartTable) -> str:
    msa = WINDOW_MSA[w]
    return f"""
        select format_date('%Y-%m', acq_month) as cohort,
               safe_divide(sum(n_adopted_clean), sum(n_observed)) as value
        from {mt(CURVES)}
        where msa = {msa} and is_cell_right_censored = false
        group by acq_month
    """


def _adoption_rate_by_segment_sql(w: Window, mt: MartTable) -> str:
    # Per-segment breakdown (D17): one fully-observed cell per (cohort, segmento) at msa=N,
    # carrying both the adoption rate (value) and the cell size (n). The min-n guard reads
    # `n` and the by-segment analyst reads `value` — both from this one governed call.
    msa = WINDOW_MSA[w]
    return f"""
        select format_date('%Y-%m', acq_month) as cohort,
               segmento as segment,
               adoption_rate as value,
               n_observed as n
        from {mt(CURVES_SEG)}
        where msa = {msa} and is_cell_right_censored = false
        order by acq_month, segmento
    """


def _adoption_rate_segment_adjusted_sql(w: Window, mt: MartTable) -> str:
    # Direct standardization: reweight each cohort's per-segment adoption rate to a FIXED
    # reference segment mix (the pooled share of each segment across all within-panel
    # cohorts). Holding the mix constant separates the dominant acquisition-mix drift
    # from the smaller genuine within-segment change (D14). sum(w) in the denominator
    # renormalizes when a cohort is missing a segment cell (e.g. right-censored).
    msa = WINDOW_MSA[w]
    return f"""
        with ref as (
            select coalesce(segmento, 'unknown') as segmento,
                   sum(cohort_size) as n_seg
            from {mt(COHORT)}
            group by segmento
        ),
        ref_w as (
            select segmento,
                   safe_divide(n_seg, sum(n_seg) over ()) as w
            from ref
        ),
        cell as (
            select acq_month, segmento, adoption_rate
            from {mt(CURVES_SEG)}
            where msa = {msa} and is_cell_right_censored = false
        )
        select format_date('%Y-%m', c.acq_month) as cohort,
               safe_divide(sum(c.adoption_rate * r.w), sum(r.w)) as value
        from cell c
        join ref_w r using (segmento)
        group by c.acq_month
    """


def _time_to_adoption_sql(_w: Window, mt: MartTable) -> str:
    # n_adopted-weighted average months from acquisition to first card, across segments.
    return f"""
        select format_date('%Y-%m', acq_month) as cohort,
               safe_divide(sum(avg_months_to_adoption * n_adopted), sum(n_adopted)) as value
        from {mt(COHORT)}
        group by acq_month
    """


def _retention_rate_sql(w: Window, mt: MartTable) -> str:
    col = WINDOW_RETENTION_COL[w]
    return f"""
        select format_date('%Y-%m', acq_month) as cohort,
               safe_divide(sum({col} * n_adopted), sum(n_adopted)) as value
        from {mt(COHORT)}
        group by acq_month
    """


def _funnel_conversion_sql(w: Window, mt: MartTable) -> str:
    if w is Window.ACQUIRED_TO_ADOPTED:
        num = "countif(is_adopted_clean)"
        den = "count(*)"
    else:  # ADOPTED_TO_RETAINED
        num = "countif(is_adopted_clean and retained_3m)"
        den = "countif(is_adopted_clean)"
    return f"""
        select format_date('%Y-%m', acq_month) as cohort,
               safe_divide({num}, {den}) as value
        from {mt(CUSTOMER)}
        where is_within_panel_cohort = true
        group by acq_month
    """


def _segment_mix_sql(_w: Window, mt: MartTable) -> str:
    # Compositional: rows of (cohort, dimension, share) — each segment's share of the
    # acquisition cohort. This is the metric that makes the mix drift legible.
    return f"""
        select format_date('%Y-%m', acq_month) as cohort,
               coalesce(segmento, 'unknown') as dimension,
               safe_divide(
                   cohort_size,
                   sum(cohort_size) over (partition by acq_month)
               ) as share
        from {mt(COHORT)}
        order by acq_month, dimension
    """


_MSA_WINDOWS = (Window.MSA_3, Window.MSA_6, Window.MSA_12)
_RET_WINDOWS = (Window.RET_1M, Window.RET_2M, Window.RET_3M)
_FUNNEL_WINDOWS = (Window.ACQUIRED_TO_ADOPTED, Window.ADOPTED_TO_RETAINED)

_RIGHT_CENSOR_CAVEAT = (
    "Only fully-observed cells are included; right-censored cohort-months (acq_month + "
    "window > 2016-05 panel end) are excluded, not silently understated."
)
_CLEAN_NUMERATOR_CAVEAT = (
    "Numerator is is_adopted_clean — left-censored customers (already holding the card at "
    "first observation, 0.06% of the panel) are excluded."
)


METRICS: dict[str, Metric] = {
    m.id: m
    for m in [
        Metric(
            id="cohort_size",
            label="Cohort size",
            description="Number of customers acquired in the cohort (within-panel acquirees).",
            unit="count",
            valid_windows=(Window.LIFETIME,),
            build_sql=_cohort_size_sql,
        ),
        Metric(
            id="adoption_rate",
            label="Card-adoption rate",
            description=(
                "Clean card adopters divided by cohort size at N months-since-acquisition."
            ),
            unit="rate",
            valid_windows=_MSA_WINDOWS,
            build_sql=_adoption_rate_sql,
            build_segment_sql=_adoption_rate_by_segment_sql,
            caveats=(_CLEAN_NUMERATOR_CAVEAT, _RIGHT_CENSOR_CAVEAT),
        ),
        Metric(
            id="adoption_rate_segment_adjusted",
            label="Card-adoption rate (segment-adjusted)",
            description=(
                "Blended adoption rate at N months-since-acquisition, reweighted to a "
                "fixed reference segment mix (pooled across all cohorts). Holds segment "
                "mix constant so acquisition-mix drift cannot masquerade as a change in "
                "the card offer — the D14 mix-decomposition metric."
            ),
            unit="rate",
            valid_windows=_MSA_WINDOWS,
            build_sql=_adoption_rate_segment_adjusted_sql,
            caveats=(
                _CLEAN_NUMERATOR_CAVEAT,
                _RIGHT_CENSOR_CAVEAT,
                "Reference mix = pooled segment shares across all within-panel cohorts; "
                "compare against adoption_rate to read the mix effect vs genuine change.",
            ),
        ),
        Metric(
            id="time_to_adoption",
            label="Time to adoption",
            description=(
                "Average months from acquisition to first card, among clean adopters "
                "(n_adopted-weighted across segments). Anchor-independent."
            ),
            unit="ratio",
            valid_windows=(Window.LIFETIME,),
            build_sql=_time_to_adoption_sql,
            caveats=(
                _CLEAN_NUMERATOR_CAVEAT,
                "Panel gaps can inflate time-to-adoption by making a flip appear one "
                "month late; see share_with_panel_gaps in mart_cohort_adoption.",
            ),
        ),
        Metric(
            id="retention_rate",
            label="Card-retention rate",
            description=(
                "Share of clean adopters still holding the card N months after first "
                "adoption. Monthly retention granularity."
            ),
            unit="rate",
            valid_windows=_RET_WINDOWS,
            build_sql=_retention_rate_sql,
            caveats=(
                "Retention is measured relative to first adoption month, not cohort "
                "month; late cohorts near the panel end are lower bounds.",
            ),
        ),
        Metric(
            id="funnel_conversion",
            label="Funnel conversion",
            description=(
                "Stage-to-stage conversion: acquired_to_adopted (adopted / acquired) or "
                "adopted_to_retained (retained at 3m / adopted)."
            ),
            unit="rate",
            valid_windows=_FUNNEL_WINDOWS,
            build_sql=_funnel_conversion_sql,
            caveats=(
                _CLEAN_NUMERATOR_CAVEAT,
                "adopted_to_retained uses 3-month retention; late cohorts are truncated "
                "by the May 2016 panel end.",
            ),
        ),
        Metric(
            id="segment_mix",
            label="Acquisition segment mix",
            description=(
                "Each segment's share of the acquisition cohort. First-class because the "
                "acquisition-mix drift (from ~85% PARTICULARES to ~76% UNIVERSITARIO "
                "across 2015) is the lead finding, not a footnote."
            ),
            unit="composition",
            valid_windows=(Window.LIFETIME,),
            build_sql=_segment_mix_sql,
            compositional=True,
            caveats=(
                "Shares sum to 1 per cohort; 'unknown' captures NULL segmento in source.",
            ),
        ),
    ]
}
