"""The Phase-3 agent layer: the tools edge, the deterministic critic, and the ADK pipeline.

Everything here sits ON TOP of the framework-neutral `semantic/` package — it wraps the four
governed tools (text-to-metric, never text-to-SQL), it never redefines a metric. The critic
and the numeric-faithfulness check are plain Python (no LLM); only the planner, analysts, and
narrator are LLM agents.
"""
