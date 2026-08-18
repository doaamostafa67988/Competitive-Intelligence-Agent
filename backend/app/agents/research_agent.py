"""
Research Agent
--------------
Role: uses MCP tools (web/news search, pricing-page fetch, career-page scrape)
to gather fresh raw data on each tracked competitor, then uses the LLM to
turn noisy page/article text into structured RawObservation records.
"""
from __future__ import annotations
import logging
import uuid
from typing import List
from app.mcp.mcp_client import call_tool
from app.agents.llm import call_llm, extract_json
from app.models.schemas import RawObservation, SourceType
from app.services.chunking import chunk_text
from app.services.embeddings import embed_documents
from app.services.guardrails import check_contextual_compliance, check_input_text
from app.services.logging_utils import truncate_for_log
from app.db.qdrant_client import get_vector_store

rag_logger = logging.getLogger("rag")  # before/after chunking + before/after indexing, separate from llm.steps

EXTRACTION_SYSTEM_PROMPT = """You are a competitive-intelligence research analyst.
Given raw scraped/searched text about a competitor, extract discrete factual
observations (pricing details, product announcements, hiring signals).
Return ONLY a JSON array of objects with fields:
  competitor, source_type (one of pricing_page, press_release, job_posting,
  news_article, social_post), title, text (a concise 1-3 sentence factual
  statement, no speculation), source_url.
If nothing factual is present, return an empty array []."""


class ResearchAgent:
    def __init__(self):
        self.vector_store = get_vector_store()

    async def gather_for_competitor(
        self, competitor: str, pricing_url: str | None, careers_url: str | None
    ) -> List[RawObservation]:
        observations: List[RawObservation] = []

        # 1. News / web mentions
        news_results = await call_tool(
            "web_news_search", query=f"{competitor} pricing OR launch OR funding OR partnership", max_results=8
        )
        for article in news_results or []:
            url = article.get("url", "")
            text = article.get("snippet", "") or ""
            obs = await self._extract_observations(competitor, SourceType.NEWS_ARTICLE, url, text)
            observations.extend(obs)
            await self._index_for_semantic_search(competitor, SourceType.NEWS_ARTICLE, url, text)

        # 2. Pricing page
        if pricing_url:
            page = await call_tool("fetch_pricing_page", url=pricing_url)
            if page:
                text = page.get("text", "")
                obs = await self._extract_observations(competitor, SourceType.PRICING_PAGE, pricing_url, text)
                observations.extend(obs)
                await self._index_for_semantic_search(competitor, SourceType.PRICING_PAGE, pricing_url, text)

        # 3. Careers / hiring signals
        if careers_url:
            postings = await call_tool(
                "scrape_career_page", company=competitor, careers_url=careers_url, max_postings=25
            )
            for posting in postings or []:
                url = posting.get("source_url", careers_url)
                text = posting.get("raw_snippet", "")
                obs = await self._extract_observations(competitor, SourceType.JOB_POSTING, url, text)
                observations.extend(obs)
                await self._index_for_semantic_search(competitor, SourceType.JOB_POSTING, url, text)

        return observations

    async def _index_for_semantic_search(
        self, competitor: str, source_type: SourceType, source_url: str, raw_text: str
    ) -> None:
        """Chunk the raw source text and embed+upsert each chunk into Qdrant,
        so the Analyst Agent's vector-search leg (and any future ad-hoc
        question-answering over this data) has something to actually search.
        Chunk count is dynamic per `chunk_text` (paragraph/sentence-aware,
        not a fixed slice) - a short news snippet yields 1 chunk, a long
        pricing page yields several. Best-effort: embedding/Qdrant failures
        are logged upstream by the underlying clients and must not break
        observation extraction, so this always runs after that already
        succeeded and never raises into the caller.
        """
        source_tag = f"{competitor}|{source_type.value}|{source_url}"

        # --- before chunking ---
        rag_logger.info(
            "chunk_start source=%s raw_text_len=%d raw_text_preview=%s",
            source_tag, len(raw_text), truncate_for_log(raw_text),
        )
        chunks = chunk_text(raw_text)
        # --- after chunking ---
        rag_logger.info(
            "chunk_end source=%s chunk_count=%d chunk_lengths=%s",
            source_tag, len(chunks), [len(c) for c in chunks],
        )
        if not chunks:
            return

        try:
            vectors = await embed_documents(chunks)
        except Exception as e:
            rag_logger.info("embed_error source=%s error=%s", source_tag, e)
            return  # embedding provider unavailable/rate-limited - skip indexing this source, extraction already ran

        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            point_id = self.vector_store.upsert_text(
                chunk,
                vector,
                metadata={"competitor": competitor, "source_type": source_type.value, "source_url": source_url},
            )
            # --- index write confirmation, one line per chunk written to Qdrant ---
            rag_logger.info(
                "index_write source=%s chunk_index=%d point_id=%s chunk_text=%s",
                source_tag, i, point_id, truncate_for_log(chunk),
            )

    async def _extract_observations(
        self, competitor: str, source_type: SourceType, source_url: str, raw_text: str
    ) -> List[RawObservation]:
        # Input guardrails: skip LLM calls on empty/near-empty scraped pages
        # (login walls, 404s), and flag - without hard-blocking, see
        # guardrails.py docstring - text that looks like a prompt-injection
        # attempt planted in a competitor's own page/press content.
        if not check_contextual_compliance(raw_text):
            return []
        check_input_text(raw_text, source=f"{source_type.value}:{source_url}")

        user_prompt = f"Competitor: {competitor}\nSource URL: {source_url}\nSource type: {source_type.value}\n\nRaw text:\n{raw_text[:6000]}"
        response = await call_llm(EXTRACTION_SYSTEM_PROMPT, user_prompt, step="research_agent.extract")
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
