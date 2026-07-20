"""HTTP-level tests for the copilot FastAPI service (no live LLM).

`create_app` takes an injected `generate_answer`, so the whole request path — hardening
gates, status-code mapping, JSON shape — is exercised with a fake LLM. This verifies the
serving contract (200 ok / 400 rejected / 429 rate-limited) that Cloud Run will expose.
"""
from fastapi.testclient import TestClient

from agents.api import create_app
from agents.hardening import RateLimiter


def _client(generate=lambda q: "adoption was 0.52%", limiter=None):
    return TestClient(create_app(generate_answer=generate, limiter=limiter))


def test_health_is_ok():
    resp = _client().get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ask_happy_path_returns_the_answer():
    resp = _client().post("/ask", json={"question": "adoption rate for cohort 2015-11?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["answer"] == "adoption was 0.52%"


def test_ask_off_topic_returns_400():
    resp = _client().post("/ask", json={"question": "what's the capital of France?"})
    assert resp.status_code == 400
    assert resp.json()["reason"] == "off_topic"


def test_ask_rate_limited_returns_429():
    clock = {"t": 0.0}
    limiter = RateLimiter(per_ip=1, global_max=100, window_s=60, now=lambda: clock["t"])
    client = _client(limiter=limiter)
    client.post("/ask", json={"question": "adoption for 2015-11 a?"})
    resp = client.post("/ask", json={"question": "adoption for 2015-11 b?"})
    assert resp.status_code == 429
    assert resp.json()["reason"] == "rate_limited"
