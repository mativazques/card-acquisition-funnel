"""Runnable entrypoint for the proactive digest — the production wiring of the pipeline.

Binds the real governed tools (`TOOL_FUNCTIONS`, which hit BigQuery) and the real Gemini
generator (AI Studio free tier, D19) into `run_digest`. Airflow's post-dbt digest task
imports `generate_digest`; a human can also run it directly for a live smoke test:

    .venv-agents/bin/python -m agents.run_digest --window msa_6

Requires GEMINI_API_KEY in the environment (AI Studio free tier) or
GOOGLE_GENAI_USE_VERTEXAI=true with ADC (the documented production path). Without a key the
offline unit tests still cover every stage except the single live LLM call.
"""
from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

from agents.narrator import genai_generator
from agents.pipeline import run_digest
from agents.tools import TOOL_FUNCTIONS


def generate_digest(window: str = "msa_6", cohort: str | None = None, prior_cohort: str | None = None) -> dict:
    """Run one digest against live BigQuery + live Gemini and return the pipeline record."""
    load_dotenv()
    return run_digest(
        tools=TOOL_FUNCTIONS,
        generate=genai_generator(),
        window=window,
        cohort=cohort,
        prior_cohort=prior_cohort,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one proactive adoption digest.")
    parser.add_argument("--window", default="msa_6")
    parser.add_argument("--cohort", default=None, help="Target cohort YYYY-MM; omit to auto-select latest.")
    parser.add_argument("--prior-cohort", default=None)
    args = parser.parse_args()

    record = generate_digest(window=args.window, cohort=args.cohort, prior_cohort=args.prior_cohort)
    print(json.dumps(record, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
