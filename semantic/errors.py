"""Structured errors for the semantic layer.

Every agent path (reactive copilot, proactive ADK digest, MCP client) must never leak a
stack trace or raw SQL. Each contract violation — unknown metric, a window not valid for
a metric, a compositional metric asked to do a scalar comparison — is a `SemanticError`
carrying a machine-readable `code` and a human message, so callers can return a clean
structured error instead of a 500.
"""
from __future__ import annotations


class SemanticError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)

    def as_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}
