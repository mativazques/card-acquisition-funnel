"""Numeric-faithfulness check (D11) — plain Python, runs AFTER the narrator writes.

Every numeric token in the narrator's prose must appear in the set of figures the critic
approved. The narrator may only restate the critic's numbers, never invent or re-round one;
any token it uses that is not in the allowed set is a violation that blocks caching and flags
the digest for human review. `allowed_tokens()` derives that permitted set deterministically
from the critic struct, so the honesty check compares the prose against the same payload the
narrator was handed — nothing else.
"""
from __future__ import annotations

import re

# Dates (YYYY-MM) first so a cohort label is one token, not two numbers; then any numeric run
# with an optional %, pp, bp or x suffix and an optional leading minus.
_TOKEN = re.compile(r"\d{4}-\d{2}|-?\d[\d,]*(?:\.\d+)?\s*(?:%|pp|bp|x)?", re.IGNORECASE)


def _normalize(token: str) -> str:
    return token.lower().replace(" ", "").replace(",", "")


def extract_number_tokens(text: str) -> list[str]:
    """Every number-like token in `text`, normalized (spaces/commas stripped, lowercased)."""
    return [_normalize(m.group()) for m in _TOKEN.finditer(text) if any(c.isdigit() for c in m.group())]


def faithfulness_check(text: str, allowed: set[str]) -> dict:
    """Verify every numeric token in `text` is in the critic-approved `allowed` set."""
    allowed_norm = {_normalize(a) for a in allowed}
    seen: list[str] = []
    violations: list[str] = []
    for tok in extract_number_tokens(text):
        if tok not in allowed_norm and tok not in seen:
            violations.append(tok)
        seen.append(tok)
    return {"faithful": not violations, "violations": violations}


def pct_token(value: float) -> str:
    """Display form of a rate: a 2-decimal percentage (e.g. 0.0052 -> '0.52%'), normalized."""
    return _normalize(f"{value * 100:.2f}%")


def pp_token(value: float) -> str:
    """Display form of a delta: 2-decimal percentage points (e.g. -0.0032 -> '-0.32pp'), normalized."""
    return _normalize(f"{value * 100:.2f}pp")


def allowed_tokens(struct: dict) -> set[str]:
    """The set of numeric display tokens the narrator is permitted to restate, derived from
    the critic struct. Rates render as 2-decimal percentages, deltas as pp (signed and
    absolute), plus cell sizes, cohort labels, and the observation-window number."""
    allowed: set[str] = {_normalize(struct["cohort_month"])}
    for num in re.findall(r"\d+", struct.get("window", "")):
        allowed.add(_normalize(num))
    for f in struct.get("findings", []):
        for key in ("cohort", "prior_cohort"):
            if f.get(key):
                allowed.add(_normalize(f[key]))
        for key in ("value", "prior_value"):
            if f.get(key) is not None:
                allowed.add(pct_token(f[key]))
        if f.get("delta") is not None:
            allowed.add(pp_token(f["delta"]))
            allowed.add(pp_token(abs(f["delta"])))
        if f.get("n") is not None:
            allowed.add(_normalize(str(f["n"])))
    return allowed
