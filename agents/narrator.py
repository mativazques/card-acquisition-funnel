"""The narrator (D11) — the one LLM step in the proactive digest pipeline.

The narrator turns the critic's approved struct into a short, honest prose insight. Three
constraints are enforced structurally, not by prompt faith alone:

  1. **Struct-only input.** `build_prompt` renders text from the critic struct and nothing
     else; the raw analyst outputs (and any SQL) never reach the model.
  2. **Causality prohibition.** The system instruction forbids causal / root-cause claims —
     the dataset has no causal fields, so a "why" would be invention. If pressed, the model
     must reframe as an explicit hypothesis, not a finding.
  3. **Numeric-faithfulness gate.** After generation, every numeric token in the prose is
     checked against the critic-approved set (`allowed_tokens`). Any invented or mis-rounded
     number makes the digest non-cacheable and flags it for human review.

The LLM is injected as a `generate: Callable[[str], str]` seam. `genai_generator()` builds
the real one on the Gemini AI Studio free tier (or Vertex via GOOGLE_GENAI_USE_VERTEXAI —
same code, D19), while tests pass a canned function so they stay offline and deterministic.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from agents.faithfulness import allowed_tokens, faithfulness_check, pct_token, pp_token

CAUSALITY_PROHIBITION = (
    "You may state WHAT changed and by how much, using only the numbers given. You must NOT "
    "claim WHY it changed: no causes, drivers, root-causes, or explanations. This dataset has "
    "no causal fields, so any 'why' is speculation. If a cause seems obvious, write it as an "
    "explicit 'hypothesis to investigate', never as a finding."
)

_SYSTEM = (
    "You are a credit-card acquisition analyst writing one short, sober insight for a cockpit. "
    "Restate ONLY the figures provided — never invent, round, or recompute a number. "
    + CAUSALITY_PROHIBITION
)


def _clean_segment(segment: str | None) -> str | None:
    """Drop the numeric code prefix from a segment label ('01 - TOP' -> 'TOP') so it never
    reaches the narrator as a stray number the faithfulness gate would flag."""
    if not segment:
        return segment
    return re.sub(r"^\s*\d+\s*-\s*", "", segment).strip()


def _display_finding(f: dict) -> dict:
    """Render one critic finding as pre-formatted display strings — the exact tokens
    `allowed_tokens` will accept, so the narrator can only copy them verbatim."""
    out: dict = {"change_type": f.get("kind"), "material": f.get("material", False)}
    if f.get("segment"):
        out["segment"] = _clean_segment(f["segment"])
    for key in ("cohort", "prior_cohort"):
        if f.get(key):
            out[key] = f[key]
    if f.get("value") is not None:
        out["adoption_rate"] = pct_token(f["value"])
    if f.get("prior_value") is not None:
        out["prior_adoption_rate"] = pct_token(f["prior_value"])
    if f.get("delta") is not None:
        out["change_pp"] = pp_token(f["delta"])
    if f.get("n") is not None:
        out["cohort_cell_size"] = f["n"]
    return out


def _display_suppressed(s: dict) -> dict:
    """Render a suppression record without leaking raw counts as narratable numbers."""
    out: dict = {"reason": s.get("reason")}
    if s.get("segment"):
        out["segment"] = _clean_segment(s["segment"])
    if s.get("cohort"):
        out["cohort"] = s["cohort"]
    return out


def build_prompt(struct: dict) -> str:
    """Render the narrator prompt from the critic struct alone (constraint 1).

    Numbers are pre-formatted to their display tokens here so the model only ever copies the
    critic-approved figures — never a raw float it would re-round into a faithfulness violation.
    """
    payload = {
        "cohort_month": struct["cohort_month"],
        "observation_window": struct["window"],
        "findings": [_display_finding(f) for f in struct.get("findings", [])],
        "suppressed": [_display_suppressed(s) for s in struct.get("suppressed", [])],
        "notes": struct.get("notes", []),
    }
    return (
        f"{_SYSTEM}\n\n"
        "Critic-approved figures (the ONLY numbers you may use — copy each figure exactly as "
        "written; do not re-round, recompute, or introduce any other number):\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n\n"
        "Write 2–4 sentences summarizing the material findings for this cohort. Rates are already "
        "formatted as percentages and changes as percentage points (pp) — quote them verbatim."
    )


def narrate(struct: dict, generate: Callable[[str], str]) -> dict:
    """Generate the insight and gate caching on the numeric-faithfulness check (constraint 3)."""
    prompt = build_prompt(struct)
    prose = generate(prompt)
    check = faithfulness_check(prose, allowed_tokens(struct))
    return {
        "prose": prose,
        "faithful": check["faithful"],
        "violations": check["violations"],
        "cacheable": check["faithful"],
    }


def genai_generator(model: str = "gemini-flash-lite-latest") -> Callable[[str], str]:
    """Build the real LLM generator on Gemini (AI Studio free tier by default, D19).

    Lazy-imports google-genai so the offline pipeline/tests never require the SDK or a key.
    `genai.Client()` reads GEMINI_API_KEY for AI Studio, or the Vertex backend when
    GOOGLE_GENAI_USE_VERTEXAI=true — the same code path serves both (D6/D19).
    """
    from google import genai
    from google.genai import types

    client = genai.Client()

    def _generate(prompt: str) -> str:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0),
        )
        return (resp.text or "").strip()

    return _generate
