"""The deterministic critic — the data-honesty gate (D10). Plain Python, no LLM.

Three guards run on the resolved metric payload BEFORE the narrator sees anything. They are
CODE, not model judgment, which is what makes the honesty contract architecturally
enforceable rather than a behavioural hope:

  Guard 1 — right-censoring: a cohort is narratable only if it is fully observed at the
            window (read from the `fully_observed_*` flag, not re-derived). A right-censored
            target cohort fails the whole digest.
  Guard 2 — min-n = 50: any cohort-segment cell with n < 50 is replaced by a structured
            suppression token; its value never reaches the narrator (at n=50 a 1pp delta has
            a ~+-4pp 95% CI — too wide to narrate).
  Guard 3 — materiality: a cohort-over-cohort delta is a "finding" only if
            abs(delta) >= 2pp AND abs(delta) > 1.5 x rolling SD of the prior 3 cohort deltas.
            With fewer than 3 prior deltas there is no SD to estimate, so it falls back to the
            absolute 2pp threshold only, flagged "insufficient history".

The narrator receives ONLY the struct `critique()` returns — never the raw analyst outputs.
"""
from __future__ import annotations

import statistics

MIN_N = 50
MATERIALITY_ABS = 0.02  # 2 pp, in rate units
MATERIALITY_K = 1.5
_ROUND = 6  # trims float-subtraction noise (~1e-4 pp); negligible vs the 2pp gate


# --- Guard 1 -----------------------------------------------------------------------

def is_fully_observed(cohort: str, fully_observed_map: dict[str, bool]) -> bool:
    """True only if the flag map explicitly marks this cohort fully observed."""
    return fully_observed_map.get(cohort, False) is True


# --- Guard 2 -----------------------------------------------------------------------

def apply_min_n(cell: dict, threshold: int = MIN_N) -> dict:
    """Pass a cell with n >= threshold untouched; else return a suppression token.

    The token deliberately drops `value` — a suppressed cell's rate must not leak downstream.
    """
    if cell["n"] < threshold:
        return {"suppressed": True, "reason": "min_n", "segment": cell["segment"], "n": cell["n"]}
    return cell


# --- Guard 3 -----------------------------------------------------------------------

def consecutive_deltas(series: list[dict]) -> list[dict]:
    """Turn an ascending [{cohort, value}] series into consecutive cohort-over-cohort deltas."""
    deltas = []
    for prev, cur in zip(series, series[1:]):
        deltas.append(
            {
                "cohort": cur["cohort"],
                "prior_cohort": prev["cohort"],
                "delta": round(cur["value"] - prev["value"], _ROUND),
            }
        )
    return deltas


def assess_materiality(
    delta: float,
    prior_deltas: list[float],
    abs_threshold: float = MATERIALITY_ABS,
    k: float = MATERIALITY_K,
) -> dict:
    """Two-part materiality verdict with the <3-history fallback to absolute-only."""
    abs_delta = abs(delta)
    if len(prior_deltas) < 3:
        return {
            "material": abs_delta >= abs_threshold,
            "abs_delta": abs_delta,
            "threshold_abs": abs_threshold,
            "sd": None,
            "threshold_sd": None,
            "insufficient_history": True,
            "note": "insufficient history for materiality assessment",
        }
    sd = statistics.stdev(prior_deltas[-3:])
    threshold_sd = k * sd
    return {
        "material": abs_delta >= abs_threshold and abs_delta > threshold_sd,
        "abs_delta": abs_delta,
        "threshold_abs": abs_threshold,
        "sd": sd,
        "threshold_sd": threshold_sd,
        "insufficient_history": False,
        "note": None,
    }


# --- Composed critic struct --------------------------------------------------------

def critique(
    window: str,
    cohort: str,
    prior_cohort: str,
    blended_series: list[dict],
    target_cells: list[dict],
    prior_cells: list[dict],
    fully_observed_map: dict[str, bool],
) -> dict:
    """Run the three guards for one target cohort and emit the narrator-facing struct.

    `blended_series` is the ascending per-cohort adoption_rate series (already fully-observed);
    `target_cells` / `prior_cells` are the per-segment cells for the target and prior cohorts.
    Returns findings (each carrying a `material` flag), suppression records, notes, and a
    `critic_passed` gate. The narrator must consume ONLY this struct.
    """
    struct = {
        "cohort_month": cohort,
        "window": window,
        "findings": [],
        "suppressed": [],
        "notes": [],
        "critic_passed": True,
    }

    # Guard 1: never narrate a right-censored target cohort.
    if not is_fully_observed(cohort, fully_observed_map):
        struct["suppressed"].append({"reason": "right_censored", "cohort": cohort})
        struct["critic_passed"] = False
        return struct

    values = {r["cohort"]: r["value"] for r in blended_series}
    deltas = consecutive_deltas(blended_series)
    target_delta = next((d for d in deltas if d["cohort"] == cohort), None)
    prior_deltas = [d["delta"] for d in deltas if d["cohort"] < cohort]

    if target_delta is not None:
        mat = assess_materiality(target_delta["delta"], prior_deltas)
        struct["findings"].append(
            {
                "kind": "blended_delta",
                "metric": "adoption_rate",
                "window": window,
                "cohort": cohort,
                "prior_cohort": target_delta["prior_cohort"],
                "value": values.get(cohort),
                "prior_value": values.get(target_delta["prior_cohort"]),
                "delta": target_delta["delta"],
                "material": mat["material"],
                "materiality": mat,
            }
        )
        if mat["insufficient_history"]:
            struct["notes"].append(mat["note"])

    target_by_seg = _keep_or_suppress(target_cells, struct["suppressed"])
    prior_by_seg = _keep_or_suppress(prior_cells, struct["suppressed"])

    for seg, tcell in target_by_seg.items():
        pcell = prior_by_seg.get(seg)
        if pcell is None:
            continue
        delta = round(tcell["value"] - pcell["value"], _ROUND)
        mat = assess_materiality(delta, prior_deltas=[])  # one pair only -> absolute fallback
        struct["findings"].append(
            {
                "kind": "segment_delta",
                "metric": "adoption_rate",
                "window": window,
                "segment": seg,
                "cohort": cohort,
                "prior_cohort": prior_cohort,
                "value": tcell["value"],
                "prior_value": pcell["value"],
                "n": tcell["n"],
                "delta": delta,
                "material": mat["material"],
                "materiality": mat,
            }
        )

    return struct


def _keep_or_suppress(cells: list[dict], suppressed: list[dict]) -> dict[str, dict]:
    kept: dict[str, dict] = {}
    for cell in cells:
        checked = apply_min_n(cell)
        if checked.get("suppressed"):
            suppressed.append(checked)
        else:
            kept[cell["segment"]] = cell
    return kept
