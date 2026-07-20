"""Copilot hardening L1–L4 (D-hardening) — deterministic, no LLM, no network.

These are the cheap defenses that run BEFORE any token is spent, so the free-tier copilot
stays honest and $0-safe:

  L1 `check_on_topic`   — a two-part router: block obvious prompt-injection, then require the
                          question to touch the governed domain (metric ids/labels + a small
                          fixed vocabulary). Off-topic and injection questions never reach the LLM.
  L2 `enforce_input_cap`— bound request size; paired with `max_output_tokens` on the model.
  L3 `RateLimiter`      — per-IP and global fixed-window ceilings, clock injected for testing.
  L4 `AnswerCache`      — LRU over normalized questions, so repeats are free.

The router derives its allow-list from the governed metric registry, so it can never drift
from the metrics the copilot can actually answer.
"""
from __future__ import annotations

import re
import time
from collections import OrderedDict
from typing import Callable

from semantic import list_metrics

_INJECTION_PATTERNS = [
    r"ignore (all |the )?previous",
    r"disregard (all |the )?(previous|above)",
    r"system prompt",
    r"reveal your (instructions|prompt)",
    r"you are now",
    r"act as",
    r"jailbreak",
]

_DOMAIN_VOCAB = {
    "adoption", "cohort", "vintage", "retention", "retain", "segment", "segmento",
    "funnel", "acquisition", "acquired", "adopted", "window", "msa", "rate", "metric",
    "card", "credit",
}


def _domain_terms() -> set[str]:
    terms = set(_DOMAIN_VOCAB)
    for m in list_metrics():
        terms.add(m["id"].lower())
        for word in re.findall(r"[a-z]+", m["label"].lower()):
            if len(word) > 3:
                terms.add(word)
    return terms


def check_on_topic(question: str) -> dict:
    """L1 router: reject injection first, then require a governed-domain term."""
    q = question.lower()
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, q):
            return {"on_topic": False, "reason": "injection"}
    tokens = set(re.findall(r"[a-z]+", q))
    if tokens & _domain_terms():
        return {"on_topic": True, "reason": None}
    return {"on_topic": False, "reason": "off_topic"}


def enforce_input_cap(question: str, max_chars: int = 500) -> str:
    """L2: reject an oversized question rather than truncating (truncation changes meaning)."""
    if len(question) > max_chars:
        raise ValueError(f"question exceeds the {max_chars}-character limit")
    return question


class RateLimiter:
    """L3: fixed-window per-IP and global ceilings. `now` is injectable for deterministic tests."""

    def __init__(self, per_ip: int = 30, global_max: int = 300, window_s: int = 60,
                 now: Callable[[], float] = time.monotonic) -> None:
        self._per_ip = per_ip
        self._global_max = global_max
        self._window_s = window_s
        self._now = now
        self._window_start = now()
        self._ip_counts: dict[str, int] = {}
        self._global_count = 0

    def _roll_if_needed(self) -> None:
        if self._now() - self._window_start >= self._window_s:
            self._window_start = self._now()
            self._ip_counts.clear()
            self._global_count = 0

    def allow(self, ip: str) -> bool:
        self._roll_if_needed()
        if self._global_count >= self._global_max:
            return False
        if self._ip_counts.get(ip, 0) >= self._per_ip:
            return False
        self._ip_counts[ip] = self._ip_counts.get(ip, 0) + 1
        self._global_count += 1
        return True


class AnswerCache:
    """L4: LRU cache over whitespace/case-normalized questions."""

    def __init__(self, maxsize: int = 128) -> None:
        self._maxsize = maxsize
        self._store: "OrderedDict[str, str]" = OrderedDict()

    @staticmethod
    def _key(question: str) -> str:
        return re.sub(r"\s+", " ", question.strip().lower())

    def get(self, question: str) -> str | None:
        key = self._key(question)
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, question: str, answer: str) -> None:
        key = self._key(question)
        self._store[key] = answer
        self._store.move_to_end(key)
        if len(self._store) > self._maxsize:
            self._store.popitem(last=False)
