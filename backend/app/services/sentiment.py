"""
Sentiment scoring (bonus feature) for competitor announcements. Cheap
LLM-based classification used when writing Announcement nodes so the graph
and brief can show tone alongside content.
"""
from __future__ import annotations
from app.agents.llm import call_llm

SENTIMENT_SYSTEM_PROMPT = """Classify the overall tone of this competitor
announcement as one of: positive, neutral, negative, promotional-hype.
Respond with ONLY the single label, nothing else."""


async def score_sentiment(announcement_text: str) -> str:
    label = await call_llm(SENTIMENT_SYSTEM_PROMPT, announcement_text[:2000], max_tokens=10, step="sentiment.score")
    return label.strip().lower()
