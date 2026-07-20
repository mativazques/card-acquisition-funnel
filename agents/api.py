"""FastAPI serving layer for the reactive copilot — self-hosted, Cloud Run scale-to-zero.

One `POST /ask` endpoint runs a question through `copilot.answer` (the L1–L4 hardening gates
plus the injected LLM) and maps the result to an HTTP status: 200 ok, 400 rejected
(off-topic / injection / too long), 429 rate-limited. `create_app` accepts an injected
`generate_answer`/`cache`/`limiter` so the HTTP contract is testable without a live LLM; in
production the generator defaults to the ADK tool-calling loop (`adk_generator`, built lazily
so import and health checks never need a Gemini key).
"""
from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agents.copilot import answer
from agents.hardening import AnswerCache, RateLimiter

_STATUS_CODE = {"ok": 200, "rejected": 400, "rate_limited": 429}


class AskRequest(BaseModel):
    question: str


def create_app(
    generate_answer: Callable[[str], str] | None = None,
    cache: AnswerCache | None = None,
    limiter: RateLimiter | None = None,
) -> FastAPI:
    """Build the copilot API. Injectable deps default to a lazy ADK generator + shared guards."""
    app = FastAPI(title="Card Acquisition Copilot", version="1.0")
    app.state.cache = cache if cache is not None else AnswerCache(maxsize=256)
    app.state.limiter = limiter if limiter is not None else RateLimiter(per_ip=30, global_max=300)
    app.state.generator = generate_answer  # None -> built on first use (needs a Gemini key)

    def _generator() -> Callable[[str], str]:
        if app.state.generator is None:
            from agents.copilot import adk_generator

            app.state.generator = adk_generator()
        return app.state.generator

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/ask")
    def ask(body: AskRequest, request: Request) -> JSONResponse:
        client_ip = request.client.host if request.client else "anon"
        result = answer(
            body.question,
            generate_answer=_generator(),
            client_ip=client_ip,
            cache=app.state.cache,
            limiter=app.state.limiter,
        )
        return JSONResponse(result, status_code=_STATUS_CODE[result["status"]])

    return app


# Module-level app for `uvicorn agents.api:app` (Cloud Run). The generator is built lazily
# on the first /ask, so import and /health never need a Gemini key.
app = create_app()
