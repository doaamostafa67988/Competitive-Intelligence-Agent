"""
Guardrails applied at the boundaries of every agent: input guardrails run on
raw external text (and user-submitted questions) before it reaches an LLM;
output guardrails run on parsed LLM output before it is written to
Neo4j/Postgres/Qdrant or sent out over Telegram/the API. This mirrors the
input/output split described in "What are Agentic Guardrails?"
(https://medium.com/@tahirbalarabe2/what-are-agentic-guardrails-249ecfc50d0a):
input guardrails filter what goes into the agent, output guardrails filter
what comes out.

Deliberately cheap/deterministic (regex + structural checks), not a second
LLM call per guardrail - that would double LLM cost and latency on every
single step this pipeline already runs. These catch the concrete failure
modes this codebase is actually exposed to (prompt injection from scraped
pages, malformed JSON crashing graph writes, PII leaking into a public
Telegram channel) - this is not a general-purpose moderation system.
"""
from __future__ import annotations
import logging
import re
from typing import Any

logger = logging.getLogger("guardrails")

# Input guardrail: prompt-injection heuristics. Scraped competitor pages and
# news snippets are untrusted text that gets concatenated straight into an
# LLM prompt (research_agent.py) - a competitor page containing text like
# "ignore previous instructions" is exactly the injection vector the source
# article warns about.
_INJECTION_PATTERNS = [
    re.compile(r"ignore (all|any|previous|prior) (instructions|rules)", re.I),
    re.compile(r"disregard (the |your )?(system|above) (prompt|instructions)", re.I),
    re.compile(r"you are now (a|an) ", re.I),
    re.compile(r"reveal (your|the) (system )?prompt", re.I),
    re.compile(r"new instructions\s*:", re.I),
    re.compile(r"</?(system|assistant)>", re.I),
]

# Output guardrail: sensitive-data leakage filter, applied to anything about
# to leave the system (Telegram posts, API responses built from LLM text).
_PII_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "card_like": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "ssn_like": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}


def check_contextual_compliance(raw_text: str, min_length: int = 40) -> bool:
    """Input guardrail: reject text too short/empty to plausibly contain a
    real observation (blank pages, login walls, 404s) before it's worth an
    LLM call. Returns True if the text is worth processing."""
    return len(raw_text.strip()) >= min_length


def check_input_text(text: str, source: str) -> bool:
    """Input guardrail: flag likely prompt-injection attempts in untrusted
    external text before it's sent to an LLM. Returns False when a pattern
    matches; callers log and may still choose to proceed with reduced trust
    rather than silently dropping a competitor's real update on a false
    positive - see docstring above on cost of hard-blocking scraped content.
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning("prompt_injection_suspected source=%s pattern=%r", source, pattern.pattern)
            return False
    return True


def check_output_json_schema(data: Any, required_keys: set[str], step: str) -> bool:
    """Output guardrail: structured-output validation. False means `data`
    isn't a dict containing every required key - callers must treat False
    exactly like an unparseable LLM response (skip this item, don't write a
    partial/malformed record to Neo4j/Postgres)."""
    if not isinstance(data, dict):
        logger.warning("output_schema_violation step=%s reason=not_a_dict got=%s", step, type(data).__name__)
        return False
    missing = required_keys - set(data.keys())
    if missing:
        logger.warning("output_schema_violation step=%s missing_keys=%s", step, missing)
        return False
    return True


def redact_pii(text: str, step: str) -> str:
    """Output guardrail: redact (not block) matches before text leaves the
    system via Telegram or an API response. Redacting rather than dropping
    the whole message avoids losing a real alert to a false positive (e.g.
    a support email mentioned in a legitimate press release)."""
    redacted = text
    for label, pattern in _PII_PATTERNS.items():
        if pattern.search(redacted):
            logger.warning("pii_redacted step=%s type=%s", step, label)
            redacted = pattern.sub(f"[REDACTED_{label.upper()}]", redacted)
    return redacted


def check_answer_grounded(tools_used: list[str], retrieved_items: list[dict], step: str) -> bool:
    """Output guardrail specific to the Q&A Agent: if a tool was invoked
    but every result was empty or an error, the LLM had nothing real to
    ground its answer in and should not be presented to the user as a
    confident answer. Returns True when either no tool call was needed at
    all (a genuinely out-of-scope question, where the LLM correctly
    answered without data), or at least one tool call returned real
    (non-error, non-empty) data. This is a presence check, not a semantic
    check - it catches "answered from nothing" but not "answered from real
    data, worded wrong"; see qa_agent.py's `sources` field, which lets the
    user verify the actual retrieved data themselves for the latter."""
    if not tools_used:
        return True
    if not retrieved_items:
        logger.warning("qa_answer_ungrounded step=%s reason=no_retrieved_items", step)
        return False
    has_real_data = any(isinstance(item, dict) and "error" not in item for item in retrieved_items)
    if not has_real_data:
        logger.warning("qa_answer_ungrounded step=%s reason=all_items_errored", step)
    return has_real_data
