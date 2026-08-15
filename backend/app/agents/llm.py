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
import re
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("llm")


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


async def call_llm(system: str, user: str, max_tokens: int = 2000) -> str:
    """
    Resilient by design: if the provider call fails (rate limit, quota
    exhausted, transient network error, etc.) this logs the failure and
    returns "" instead of raising. Callers already treat an unparseable/
    empty response as "no observations extracted" (extract_json raises
    JSONDecodeError -> caught -> []), so one competitor/source hitting a
    rate limit no longer kills the whole pipeline run.
    """
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
        return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning("LLM call failed (%s), skipping this extraction: %s", settings.LLM_PROVIDER, e)
        return ""


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
