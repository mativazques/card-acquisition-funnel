"""The reactive copilot — minimal single-agent text-to-metric Q&A (secondary feature).

`answer()` composes the four hardening gates around one injected LLM call, in a fixed order
so a rejected, rate-limited, or cached request never spends a token:

    L2 input cap  ->  L1 on-topic router  ->  L3 rate limit  ->  L4 answer cache  ->  LLM

The LLM is injected as `generate_answer: Callable[[str], str]`, so this orchestration is
tested offline. In production the generator is an ADK `LlmAgent` bound to the four governed
tools (`build_governed_agent`) — this is where ADK earns its place (D6): a genuine multi-turn
tool-calling loop, unlike the digest whose orchestration is deterministic. Same governed
tools as BI and the digest (D7 text-to-metric), self-hosted, Gemini free tier (D19).
"""
from __future__ import annotations

from typing import Callable

from agents.hardening import AnswerCache, RateLimiter, check_on_topic, enforce_input_cap

_SYSTEM = (
    "You are the card-acquisition cockpit copilot. Answer ONLY from the governed metric tools "
    "(list_metrics, query_metric, compare_cohorts, explain_metric) — never invent numbers or "
    "write SQL. State WHAT the metrics show; do NOT claim WHY (no causes or root-causes — the "
    "data has no causal fields). If a cause seems implied, offer it as a hypothesis to "
    "investigate, not a finding. If a question is outside these metrics, say so plainly."
)


def answer(
    question: str,
    generate_answer: Callable[[str], str],
    client_ip: str = "anon",
    cache: AnswerCache | None = None,
    limiter: RateLimiter | None = None,
    max_chars: int = 500,
) -> dict:
    """Run one copilot turn through the hardening gates and (only if all pass) the LLM."""
    # L2 — input cap.
    try:
        enforce_input_cap(question, max_chars=max_chars)
    except ValueError:
        return {"status": "rejected", "reason": "too_long", "answer": None, "cached": False}

    # L1 — on-topic router.
    topic = check_on_topic(question)
    if not topic["on_topic"]:
        return {"status": "rejected", "reason": topic["reason"], "answer": None, "cached": False}

    # L3 — rate limit.
    if limiter is not None and not limiter.allow(client_ip):
        return {"status": "rate_limited", "reason": "rate_limited", "answer": None, "cached": False}

    # L4 — answer cache.
    if cache is not None:
        hit = cache.get(question)
        if hit is not None:
            return {"status": "ok", "reason": None, "answer": hit, "cached": True}

    result = generate_answer(question)
    if cache is not None:
        cache.put(question, result)
    return {"status": "ok", "reason": None, "answer": result, "cached": False}


def build_governed_agent(model: str = "gemini-flash-lite-latest"):
    """Build the ADK LlmAgent bound to the four governed tools (real ADK tool-calling, D6).

    Lazy-imports google-adk so the offline orchestration/tests never require it. The agent
    calls only the governed tool functions, so every number it returns is registry-resolved.
    """
    from google.adk.agents import LlmAgent

    from agents.tools import (
        tool_compare_cohorts,
        tool_explain_metric,
        tool_list_metrics,
        tool_query_metric,
    )

    return LlmAgent(
        name="acquisition_copilot",
        model=model,
        instruction=_SYSTEM,
        tools=[tool_list_metrics, tool_query_metric, tool_compare_cohorts, tool_explain_metric],
    )


_APP_NAME = "acquisition_copilot"


def adk_generator(model: str = "gemini-flash-lite-latest") -> Callable[[str], str]:
    """Run the ADK agent via an in-memory Runner and return its final text (D6 tool-calling loop).

    This is the production `generate_answer` for the FastAPI service. Building the agent and
    Runner needs no credentials; only a live turn spends a Gemini call (AI Studio free tier,
    or Vertex via GOOGLE_GENAI_USE_VERTEXAI). Each turn is a fresh session — the copilot is
    stateless Q&A, not a chat.
    """
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=build_governed_agent(model), app_name=_APP_NAME)

    def _generate(question: str) -> str:
        session = runner.session_service.create_session_sync(app_name=_APP_NAME, user_id="copilot")
        message = types.Content(role="user", parts=[types.Part(text=question)])
        final = ""
        for event in runner.run(user_id="copilot", session_id=session.id, new_message=message):
            if event.is_final_response() and event.content and event.content.parts:
                final = "".join(p.text or "" for p in event.content.parts)
        return final.strip()

    return _generate
