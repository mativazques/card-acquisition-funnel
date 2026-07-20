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
from typing import Callable

from agents.faithfulness import allowed_tokens, faithfulness_check

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


def build_prompt(struct: dict) -> str:
    """Render the narrator prompt from the critic struct alone (constraint 1)."""
    payload = {
        "cohort_month": struct["cohort_month"],
        "window": struct["window"],
        "findings": struct.get("findings", []),
        "suppressed": struct.get("suppressed", []),
        "notes": struct.get("notes", []),
    }
    return (
        f"{_SYSTEM}\n\n"
        "Critic-approved figures (the ONLY numbers you may use):\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n\n"
        "Write 2–4 sentences summarizing the material findings for this cohort. "
        "Report rates as percentages and deltas in percentage points (pp), exactly as given."
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
