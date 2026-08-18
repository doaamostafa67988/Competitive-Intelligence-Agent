"""
Shared helper for keeping structured log lines from blowing up on long text
(20k-char scraped pages, chunked documents, retrieval hits). Used by the RAG
pipeline logging in research_agent.py / analyst_agent.py / qa_agent.py so
every "before/after chunking" and "before/after retrieval" log line stays
consistently capped and grep-able, the same way agents/llm.py already caps
LLM call input/output.
"""
from __future__ import annotations


def truncate_for_log(text: str, limit: int = 500) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + f"...[+{len(text) - limit} chars]"
