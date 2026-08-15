"""
Research Agent
--------------
Role: uses MCP tools (web/news search, pricing-page fetch, career-page scrape)
to gather fresh raw data on each tracked competitor, then uses the LLM to
turn noisy page/article text into structured RawObservation records.
"""
from __future__ import annotations
import uuid
from typing import List
from app.mcp.mcp_client import call_tool
from app.agents.llm import call_llm, extract_json
from app.models.schemas import RawObservation, SourceType

EXTRACTION_SYSTEM_PROMPT = """You are a competitive-intelligence research analyst.
Given raw scraped/searched text about a competitor, extract discrete factual
observations (pricing details, product announcements, hiring signals).
Return ONLY a JSON array of objects with fields:
  competitor, source_type (one of pricing_page, press_release, job_posting,
  news_article, social_post), title, text (a concise 1-3 sentence factual
  statement, no speculation), source_url.
If nothing factual is present, return an empty array []."""


class ResearchAgent:
    async def gather_for_competitor(
        self, competitor: str, pricing_url: str | None, careers_url: str | None
    ) -> List[RawObservation]:
        observations: List[RawObservation] = []

        # 1. News / web mentions
        news_results = await call_tool(
            "web_news_search", query=f"{competitor} pricing OR launch OR funding OR partnership", max_results=8
        )
        for article in news_results or []:
            obs = await self._extract_observations(
                competitor, SourceType.NEWS_ARTICLE, article.get("url", ""), article.get("snippet", "") or ""
            )
            observations.extend(obs)

        # 2. Pricing page
        if pricing_url:
            page = await call_tool("fetch_pricing_page", url=pricing_url)
            if page:
                obs = await self._extract_observations(
                    competitor, SourceType.PRICING_PAGE, pricing_url, page.get("text", "")
                )
                observations.extend(obs)

        # 3. Careers / hiring signals
        if careers_url:
            postings = await call_tool(
                "scrape_career_page", company=competitor, careers_url=careers_url, max_postings=25
            )
            for posting in postings or []:
                obs = await self._extract_observations(
                    competitor, SourceType.JOB_POSTING, posting.get("source_url", careers_url),
                    posting.get("raw_snippet", ""),
                )
                observations.extend(obs)

        return observations

    async def _extract_observations(
        self, competitor: str, source_type: SourceType, source_url: str, raw_text: str
    ) -> List[RawObservation]:
        if not raw_text.strip():
            return []
        user_prompt = f"Competitor: {competitor}\nSource URL: {source_url}\nSource type: {source_type.value}\n\nRaw text:\n{raw_text[:6000]}"
        response = await call_llm(EXTRACTION_SYSTEM_PROMPT, user_prompt)
        try:
            items = extract_json(response)
        except Exception:
            return []
        results = []
        for item in items:
            if not isinstance(item, dict):
                continue  # LLM occasionally returns a bare string/list entry - skip rather than crash
            try:
                results.append(
                    RawObservation(
                        id=str(uuid.uuid4()),
                        competitor=item.get("competitor", competitor),
                        source_type=SourceType(item.get("source_type", source_type.value)),
                        source_url=item.get("source_url", source_url),
                        title=item.get("title", "")[:300],
                        text=item.get("text", ""),
                    )
                )
            except (ValueError, TypeError):
                continue  # malformed item (e.g. unrecognized source_type) - skip rather than crash the pipeline
        return results
