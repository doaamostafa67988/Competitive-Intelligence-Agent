"""
Shared LLM client used by every agent. Centralized so model/temperature
config and JSON-extraction helpers live in one place.

Supports two interchangeable providers, picked via settings.LLM_PROVIDER
("groq" or "openai") — both SDKs expose the same chat.completions.create
interface, so call_llm() below works unchanged either way:

- Groq (https://console.groq.com) — free tier, fast open-weight models like
  llama-3.3-70b-versatile.
- OpenAI (https://platform.openai.com) — paid, models like gpt-4o-mini.

Set LLM_PROVIDER and the matching *_API_KEY in .env; LLM_MODEL should match
whichever provider you pick (e.g. "llama-3.3-70b-versatile" for Groq,
"gpt-4o-mini" for OpenAI).
"""
from __future__ import annotations
import json
import logging
import os
import re
import time
import uuid
from app.config import get_settings

settings = get_settings()

# LangSmith reads its config from process env vars, not from our Settings
# object directly - mirror the two here before `traceable` is imported so
# tracing picks up whatever's in .env without a separate export step.
if settings.LANGCHAIN_API_KEY:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true" if settings.LANGCHAIN_TRACING_V2 else "false")
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.LANGCHAIN_API_KEY)
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGCHAIN_PROJECT)

from langsmith import traceable  # noqa: E402 - must follow the env var setup above

logger = logging.getLogger("llm")
step_logger = logging.getLogger("llm.steps")  # separate logger so input/output can be filtered/routed independently


def _build_client():
    if settings.LLM_PROVIDER == "openai":
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    elif settings.LLM_PROVIDER == "groq":
        from groq import AsyncGroq
        return AsyncGroq(api_key=settings.GROQ_API_KEY)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER!r} (expected 'groq' or 'openai')")


_client = _build_client()


@traceable(name="call_llm", run_type="llm")
async def call_llm(system: str, user: str, max_tokens: int = 2000, step: str = "unknown") -> str:
    """
    Resilient by design: if the provider call fails (rate limit, quota
    exhausted, transient network error, etc.) this logs the failure and
    returns "" instead of raising. Callers already treat an unparseable/
    empty response as "no observations extracted" (extract_json raises
    JSONDecodeError -> caught -> []), so one competitor/source hitting a
    rate limit no longer kills the whole pipeline run.

    `step` tags which agent/prompt this call belongs to (e.g.
    "research_agent.extract", "fact_checker.cluster") so every call can be
    traced end-to-end: this is the single chokepoint every agent's LLM work
    passes through, so logging here covers all of them without touching
    each agent's business logic.
    """
    call_id = uuid.uuid4().hex[:8]
    started = time.monotonic()
    step_logger.info(
        "llm_call_start id=%s step=%s system=%s user=%s",
        call_id, step, _truncate(system), _truncate(user),
    )
    try:
        resp = await _client.chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            temperature=settings.LLM_TEMPERATURE,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = resp.choices[0].message.content or ""
        step_logger.info(
            "llm_call_end id=%s step=%s duration_ms=%d output=%s",
            call_id, step, int((time.monotonic() - started) * 1000), _truncate(content),
        )
        return content
    except Exception as e:
        logger.warning("LLM call failed (%s), skipping this extraction: %s", settings.LLM_PROVIDER, e)
        step_logger.info(
            "llm_call_error id=%s step=%s duration_ms=%d error=%s",
            call_id, step, int((time.monotonic() - started) * 1000), e,
        )
        return ""


@traceable(name="call_llm_with_tools", run_type="chain")
async def call_llm_with_tools(
    system: str,
    user: str,
    tools: list[dict],
    tool_executor,
    max_tokens: int = 1500,
    step: str = "unknown",
    max_rounds: int = 3,
) -> str:
    """
    Multi-round tool-calling loop for agents that need to decide *which*
    read-only lookup to run based on free-text input (the Q&A agent), as
    opposed to every other agent here which always runs the same fixed
    sequence of calls. `tools` is an OpenAI-style function-calling schema;
    `tool_executor(name, args) -> Any` is called for each tool_call the
    model requests and must itself enforce whatever safety limits apply to
    that tool (e.g. only pre-approved Cypher templates - see
    db/neo4j_client.py). This function only owns the conversation loop, not
    tool safety.

    Capped at `max_rounds` model round-trips so a model that keeps calling
    tools without ever answering can't loop forever; returns "" if it never
    produces a final text answer within the cap (callers treat "" the same
    as any other empty LLM response).
    """
    call_id = uuid.uuid4().hex[:8]
    started = time.monotonic()
    step_logger.info("llm_tool_call_start id=%s step=%s user=%s", call_id, step, _truncate(user))

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        for round_num in range(max_rounds):
            resp = await _client.chat.completions.create(
                model=settings.LLM_MODEL,
                max_tokens=max_tokens,
                temperature=settings.LLM_TEMPERATURE,
                messages=messages,
                tools=tools,
            )
            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                content = msg.content or ""
                step_logger.info(
                    "llm_tool_call_end id=%s step=%s rounds=%d duration_ms=%d output=%s",
                    call_id, step, round_num + 1, int((time.monotonic() - started) * 1000), _truncate(content),
                )
                return content

            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                step_logger.info("llm_tool_invoke id=%s step=%s tool=%s args=%s", call_id, step, tc.function.name, args)
                try:
                    result = await tool_executor(tc.function.name, args)
                except Exception as e:
                    result = {"error": str(e)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _truncate(json.dumps(result, default=str), limit=3000),
                })

        step_logger.info("llm_tool_call_exhausted id=%s step=%s max_rounds=%d", call_id, step, max_rounds)
        return ""
    except Exception as e:
        logger.warning("LLM tool-call loop failed (%s): %s", settings.LLM_PROVIDER, e)
        step_logger.info("llm_tool_call_error id=%s step=%s error=%s", call_id, step, e)
        return ""


def _truncate(text: str, limit: int = 1500) -> str:
    """Log bodies are capped so a 20k-char scraped pricing page doesn't
    blow up log volume; raise `limit` locally if you need the full text
    for a specific debugging session."""
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + f"...[+{len(text) - limit} chars]"


def extract_json(text: str):
    """Best-effort extraction of a JSON object/array from an LLM response that
    may include prose or markdown code fences around it."""
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidate = fenced.group(1) if fenced else text
    candidate = candidate.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # fall back to the widest {...} or [...] span in the text
        for open_c, close_c in [("{", "}"), ("[", "]")]:
            start = candidate.find(open_c)
            end = candidate.rfind(close_c)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(candidate[start : end + 1])
                except json.JSONDecodeError:
                    continue
        raise
