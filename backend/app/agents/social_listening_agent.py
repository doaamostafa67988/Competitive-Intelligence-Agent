"""
Social Listening Agent
-----------------------
Role: ad-hoc scan (not part of the weekly Research->...->Change-Log
pipeline) that, given up to 5 competitor names, pulls recent Twitter/X,
LinkedIn, and Reddit posts/mentions via the `social_listening_search` MCP
tool (SerpAPI site-search) and has the LLM score each competitor's social
presence across five dimensions:
  tone_voice, pricing_clarity, hiring_signal, social_momentum, content_velocity

This answers a different question than the weekly brief ("what does their
social presence look and feel like right now") so it's kept as its own
agent/endpoint that runs on demand, in seconds, rather than feeding the
knowledge graph.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

from app.mcp.mcp_client import call_tool
from app.agents.llm import call_llm, extract_json
from app.models.schemas import SocialPost, SocialPlatform, DimensionScore, SocialScorecard

SCORING_SYSTEM_PROMPT = """You are a social-media competitive analyst. You
are given a batch of recent Twitter/X, LinkedIn, and Reddit posts/mentions
about ONE competitor (title, url, snippet, platform, date for each).

Score the competitor's social presence on five dimensions, each 1-10:
- tone_voice: how distinctive/consistent/on-brand their voice reads across
  posts (1 = generic or absent, 10 = highly distinctive and consistent)
- pricing_clarity: how openly and clearly pricing is discussed or
  referenced in their social content and mentions (1 = opaque/never
  discussed, 10 = consistently clear and upfront)
- hiring_signal: strength of hiring/growth signal visible in the posts
  (job posts shared, "we're hiring", team-growth announcements)
  (1 = no signal, 10 = strong active hiring push visible)
- social_momentum: engagement/buzz/volume of *other people* talking about
  them relative to what you'd expect for a company their size
  (1 = quiet/no buzz, 10 = high buzz)
- content_velocity: how frequently THEY appear to be posting/publishing,
  judged from the date spread and count of the sample
  (1 = stale/rare, 10 = very frequent)

If a dimension has no evidence in the supplied posts, still return a score
(use 1-3) and say so plainly in the rationale rather than inventing signal.
Ground every rationale in specifics from the supplied posts - do not
speculate beyond what's there.

Return ONLY a JSON object:
{
  "tone_voice": {"score": 1-10, "label": "3-6 word label", "rationale": "1-2 sentences"},
  "pricing_clarity": {"score": 1-10, "label": "3-6 word label", "rationale": "1-2 sentences"},
  "hiring_signal": {"score": 1-10, "label": "3-6 word label", "rationale": "1-2 sentences"},
  "social_momentum": {"score": 1-10, "label": "3-6 word label", "rationale": "1-2 sentences"},
  "content_velocity": {"score": 1-10, "label": "3-6 word label", "rationale": "1-2 sentences"},
  "overall_summary": "3-4 sentence synthesis of what this competitor's social presence tells you"
}"""

_DIMENSION_KEYS = ["tone_voice", "pricing_clarity", "hiring_signal", "social_momentum", "content_velocity"]


class SocialListeningAgent:
    async def scan_competitor(self, competitor: str, platforms: Optional[List[str]] = None) -> SocialScorecard:
        raw_results = await call_tool("social_listening_search", competitor=competitor, platforms=platforms)
        posts = self._parse_posts(raw_results or [])

        if not posts:
            empty = DimensionScore(
                score=1, label="No data found",
                rationale="No social mentions were returned for this search window.",
            )
            return SocialScorecard(
                id=str(uuid.uuid4()),
                competitor=competitor,
                scanned_at=datetime.utcnow(),
                platforms_covered=[],
                tone_voice=empty, pricing_clarity=empty, hiring_signal=empty,
                social_momentum=empty, content_velocity=empty,
                overall_summary=(
                    f"No recent Twitter/X, LinkedIn, or Reddit mentions of {competitor} were found "
                    "in the past month. This may mean low social activity, or that SERPAPI_KEY "
                    "isn't configured on the backend."
                ),
                sample_posts=[],
            )

        response = await call_llm(SCORING_SYSTEM_PROMPT, self._build_user_prompt(competitor, posts), max_tokens=1200)
        try:
            data = extract_json(response)
        except Exception:
            data = {}

        platforms_covered = sorted({p.platform for p in posts}, key=lambda p: p.value)

        return SocialScorecard(
            id=str(uuid.uuid4()),
            competitor=competitor,
            scanned_at=datetime.utcnow(),
            platforms_covered=platforms_covered,
            tone_voice=self._dim(data, "tone_voice"),
            pricing_clarity=self._dim(data, "pricing_clarity"),
            hiring_signal=self._dim(data, "hiring_signal"),
            social_momentum=self._dim(data, "social_momentum"),
            content_velocity=self._dim(data, "content_velocity"),
            overall_summary=data.get("overall_summary") or (response[:600] if response else "No summary generated."),
            sample_posts=posts[:12],
        )

    async def scan_many(self, competitors: List[str], platforms: Optional[List[str]] = None) -> List[SocialScorecard]:
        # Sequential, not gathered concurrently: keeps SerpAPI + LLM calls
        # well under free/low-tier rate limits when scanning up to 5
        # competitors x 3 platforms in one request.
        return [await self.scan_competitor(name, platforms) for name in competitors[:5]]

    @staticmethod
    def _parse_posts(raw_results: list[dict]) -> List[SocialPost]:
        posts: List[SocialPost] = []
        for item in raw_results:
            try:
                posts.append(
                    SocialPost(
                        platform=SocialPlatform(item.get("platform", "twitter")),
                        title=(item.get("title") or "")[:300],
                        url=item.get("url", ""),
                        snippet=item.get("snippet", ""),
                        published_at=item.get("published_at"),
                    )
                )
            except ValueError:
                continue  # unrecognized platform value - skip rather than fail the whole scan
        return posts

    @staticmethod
    def _build_user_prompt(competitor: str, posts: List[SocialPost]) -> str:
        posts_txt = "\n".join(
            f"- [{p.platform.value}] {p.title} — {p.snippet} ({p.published_at or 'no date'}) {p.url}"
            for p in posts
        )
        return f"Competitor: {competitor}\n\nPosts/mentions:\n{posts_txt}"

    @staticmethod
    def _dim(data: dict, key: str) -> DimensionScore:
        d = data.get(key) or {}
        try:
            return DimensionScore(
                score=int(d.get("score", 3)),
                label=(d.get("label") or "Unclear")[:80],
                rationale=d.get("rationale") or "Not enough signal to assess confidently.",
            )
        except Exception:
            return DimensionScore(score=3, label="Unclear", rationale="Not enough signal to assess confidently.")
