"""The `window` enum contract — the funnel vocabulary is MSA, not MOB.

A window scopes a metric to a point in the customer lifecycle. This project counts
**months-since-acquisition** (MSA) — elapsed months from the acquisition cohort month —
deliberately NOT flagship #1's months-on-book (MOB). Retention windows count months
after first card adoption; funnel windows name a stage pair. `lifetime` means "to the
2016-05 panel end, no cap".

This enum is the single vocabulary BI and every agent path speak; an unknown window is a
contract violation, not a silent fallback.
"""
from __future__ import annotations

from enum import Enum


class Window(str, Enum):
    # months-since-acquisition (cumulative card adoption)
    MSA_3 = "msa_3"
    MSA_6 = "msa_6"
    MSA_12 = "msa_12"
    # months after first adoption (card retention)
    RET_1M = "ret_1m"
    RET_2M = "ret_2m"
    RET_3M = "ret_3m"
    # funnel stage pairs
    ACQUIRED_TO_ADOPTED = "acquired_to_adopted"
    ADOPTED_TO_RETAINED = "adopted_to_retained"
    # no cap
    LIFETIME = "lifetime"


# msa cap per adoption window.
WINDOW_MSA: dict[Window, int] = {
    Window.MSA_3: 3,
    Window.MSA_6: 6,
    Window.MSA_12: 12,
}

# retention window -> mart column suffix.
WINDOW_RETENTION_COL: dict[Window, str] = {
    Window.RET_1M: "retention_rate_1m",
    Window.RET_2M: "retention_rate_2m",
    Window.RET_3M: "retention_rate_3m",
}


def parse_window(value: str | Window) -> Window:
    """Coerce a string to a Window, raising ValueError on a bad value."""
    if isinstance(value, Window):
        return value
    try:
        return Window(value)
    except ValueError as exc:
        raise ValueError(
            f"unknown window '{value}'; allowed: {[w.value for w in Window]}"
        ) from exc
