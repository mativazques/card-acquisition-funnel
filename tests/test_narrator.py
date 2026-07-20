"""Unit tests for the narrator (D11) — no live LLM.

The narrator is the ONLY LLM step in the digest pipeline. Its architectural constraints are
enforced in code, not hoped for in the prompt:
  (1) input is the critic struct only — the prompt is built from it and nothing else;
  (2) the system instruction forbids causal / root-cause claims;
  (3) a post-generation numeric-faithfulness check gates caching — any invented or
      mis-rounded number blocks the digest and flags it for human review.
The LLM is injected as a `generate` callable so these tests run offline and deterministically.
"""
from agents.narrator import CAUSALITY_PROHIBITION, build_prompt, narrate


def _struct():
    return {
        "cohort_month": "2015-11",
        "window": "msa_6",
        "findings": [
            {
                "kind": "blended_delta",
                "cohort": "2015-11",
                "prior_cohort": "2015-10",
                "value": 0.0052,
                "prior_value": 0.0084,
                "delta": -0.0032,
                "material": True,
            }
        ],
        "suppressed": [],
        "notes": [],
        "critic_passed": True,
    }


def test_prompt_is_built_only_from_the_struct_and_carries_the_causality_ban():
    prompt = build_prompt(_struct())
    assert "2015-11" in prompt
    assert CAUSALITY_PROHIBITION in prompt
    # the raw analyst payload never reaches the narrator; the prompt is struct-derived text
    assert "SELECT" not in prompt.upper()


def test_narrate_is_faithful_when_prose_only_restates_allowed_numbers():
    prose = "The 2015-11 cohort's blended adoption fell to 0.52% from 0.84%, a 0.32pp drop."
    out = narrate(_struct(), generate=lambda _p: prose)
    assert out["faithful"] is True
    assert out["cacheable"] is True
    assert out["violations"] == []
    assert out["prose"] == prose


def test_narrate_blocks_caching_when_the_llm_invents_a_number():
    prose = "The 2015-11 cohort collapsed to 0.19%, driven by a rate cut."
    out = narrate(_struct(), generate=lambda _p: prose)
    assert out["faithful"] is False
    assert out["cacheable"] is False
    assert "0.19%" in out["violations"]
