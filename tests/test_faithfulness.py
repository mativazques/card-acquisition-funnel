"""Unit tests for the numeric-faithfulness check (D11) — no LLM, no BigQuery.

After the narrator writes prose, every numeric token it used must appear in the set of
figures the critic approved. A number the narrator invented or mis-rounded is a faithfulness
violation that blocks caching and flags the digest for human review — no figure reaches the
cockpit that the critic did not sign off.
"""
from agents.critic import critique
from agents.faithfulness import allowed_tokens, extract_number_tokens, faithfulness_check


def test_extract_finds_percentages_dates_counts_and_pp():
    toks = set(extract_number_tokens("The 2015-11 cohort fell to 0.52% (n=2,704), down 0.32 pp."))
    assert {"2015-11", "0.52%", "2704", "0.32pp"} <= toks


def test_faithful_when_every_token_is_allowed():
    allowed = {"2015-11", "0.52%", "2704", "0.32pp"}
    out = faithfulness_check("2015-11 fell to 0.52% (n=2704), down 0.32 pp.", allowed)
    assert out["faithful"] is True
    assert out["violations"] == []


def test_hallucinated_number_is_a_violation():
    allowed = {"2015-11", "0.52%"}
    out = faithfulness_check("2015-11 fell to 0.99%.", allowed)
    assert out["faithful"] is False
    assert "0.99%" in out["violations"]


def test_rounding_mismatch_is_a_violation():
    allowed = {"0.52%"}
    out = faithfulness_check("adoption was 0.5%.", allowed)
    assert out["faithful"] is False
    assert "0.5%" in out["violations"]


def test_allowed_tokens_derives_display_forms_from_the_critic_struct():
    struct = critique(
        window="msa_6",
        cohort="2015-11",
        prior_cohort="2015-10",
        blended_series=[
            {"cohort": "2015-10", "value": 0.0084},
            {"cohort": "2015-11", "value": 0.0052},
        ],
        target_cells=[],
        prior_cells=[],
        fully_observed_map={"2015-10": True, "2015-11": True},
    )
    allowed = allowed_tokens(struct)
    assert {"0.52%", "0.84%", "2015-11", "2015-10"} <= allowed
    # the blended delta 0.0052-0.0084 = -0.32 pp must be an allowed figure
    assert "0.32pp" in allowed
