"""
Analyst / Synthesizer Agent
-----------------------------
Role: implements GraphRAG. Relationship-shaped questions ("who changed
pricing twice this quarter") are answered via Cypher graph traversal;
semantic questions ("who is talking about AI features") are answered via
vector search over announcement/press-release text in Qdrant. Both result
sets are combined and handed to the LLM to synthesize the executive brief.
"""
from __future__ import annotations
import uuid
from datetime import date, timedelta
from typing import List
from app.agents.llm import call_llm, extract_json
from app.db.neo4j_client import get_neo4j_client
from app.db.qdrant_client import get_vector_store
from app.models.schemas import CompetitiveBrief, BriefSection, VerifiedClaim, VerificationStatus

SYNTHESIS_SYSTEM_PROMPT = """You are the lead analyst producing a weekly
executive competitive-intelligence brief for a SaaS company's leadership
team. You are given: (1) confirmed claims from this week's research run,
(2) graph-traversal answers to relationship questions, (3) semantic search
hits for thematic questions, and (4) a list of unconfirmed/flagged claims
that must NOT appear as fact.

Write in clear, direct executive language. Every factual sentence must be
traceable to a supplied claim or search hit - do not invent facts. Return
ONLY a JSON object:
{
  "executive_summary": "3-5 sentence overview of the week",
  "sections": [
    {"heading": "...", "body_markdown": "...", "cited_source_urls": ["..."]}
  ]
}
Include sections for: Pricing Moves, Product & Announcements, Hiring Signals,
and Thematic Trends (e.g. AI feature messaging). Skip a section if there is
nothing to report. Never state an unconfirmed claim as settled fact - if you
reference one, explicitly say "unconfirmed" in the text."""


class AnalystAgent:
    def __init__(self):
        self.neo4j = get_neo4j_client()
        self.vector_store = get_vector_store()

    async def synthesize_brief(
        self, competitors: List[str], claims: List[VerifiedClaim], query_embedding_fn
    ) -> CompetitiveBrief:
        confirmed = [c for c in claims if c.status == VerificationStatus.CONFIRMED]
        unconfirmed = [c for c in claims if c.status == VerificationStatus.UNCONFIRMED]

        # --- Graph traversal leg: relationship questions ---
        since = (date.today() - timedelta(days=90)).isoformat()
        repeat_price_changers = self.neo4j.competitors_who_changed_price_n_times(since, n=2)

        # --- Vector search leg: semantic/thematic questions ---
        thematic_hits = []
        for theme in ["AI features", "enterprise expansion", "new integrations"]:
            try:
                embedding = await query_embedding_fn(theme)
                hits = self.vector_store.search(embedding, top_k=5)
                thematic_hits.append({"theme": theme, "hits": hits})
            except Exception:
                continue

        user_prompt = self._build_user_prompt(competitors, confirmed, unconfirmed, repeat_price_changers, thematic_hits)
        response = await call_llm(SYNTHESIS_SYSTEM_PROMPT, user_prompt, max_tokens=3000)
        try:
            data = extract_json(response)
        except Exception:
            data = {"executive_summary": response[:1000], "sections": []}

        return CompetitiveBrief(
            id=str(uuid.uuid4()),
            competitors_covered=competitors,
            executive_summary=data.get("executive_summary", ""),
            sections=[BriefSection(**s) for s in data.get("sections", [])],
            change_log=[],  # filled in by Change-Log Agent
            unconfirmed_claims=[c.claim for c in unconfirmed],
        )

    def _build_user_prompt(self, competitors, confirmed, unconfirmed, repeat_price_changers, thematic_hits) -> str:
        confirmed_txt = "\n".join(f"- [{c.competitor}] {c.claim} (sources: {', '.join(c.supporting_source_urls)})" for c in confirmed)
        unconfirmed_txt = "\n".join(f"- [{c.competitor}] {c.claim} (single source, UNCONFIRMED)" for c in unconfirmed)
        graph_txt = "\n".join(f"- {r['competitor']} changed pricing {r['changes']} times in the last 90 days" for r in repeat_price_changers)
        thematic_txt = "\n\n".join(
            f"Theme: {t['theme']}\n" + "\n".join(f"  - {h.get('competitor','?')}: {h.get('text','')[:200]}" for h in t["hits"])
            for t in thematic_hits
        )
        return (
            f"Competitors tracked this week: {', '.join(competitors)}\n\n"
            f"CONFIRMED CLAIMS:\n{confirmed_txt or 'None'}\n\n"
            f"UNCONFIRMED CLAIMS (flag, do not assert as fact):\n{unconfirmed_txt or 'None'}\n\n"
            f"GRAPH TRAVERSAL - repeat price changers (last 90 days):\n{graph_txt or 'None'}\n\n"
            f"VECTOR SEARCH - thematic hits:\n{thematic_txt or 'None'}"
        )
