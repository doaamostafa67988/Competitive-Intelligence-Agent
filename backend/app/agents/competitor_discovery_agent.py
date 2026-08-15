"""
Competitor Discovery Agent
---------------------------
Role: given the user's OWN company name, search the web for who its real
competitors/alternatives are and return a clean, deduplicated candidate
list with a short reason for each - so the user picks from suggestions
instead of typing every competitor in by hand on the Competitors page.

This is the missing first step before /competitors (which only tracks
whatever the user explicitly adds): discover -> user reviews/picks ->
existing upsert_competitor adds the chosen ones as tracked.
"""
from __future__ import annotations
from typing import List
from app.mcp.mcp_client import call_tool
from app.agents.llm import call_llm, extract_json
from app.models.schemas import CompetitorSuggestion

DISCOVERY_SYSTEM_PROMPT = """You are a market-research analyst. You are
given raw web search results (title, url, snippet) about a company's
competitors and alternatives.

Extract a clean, deduplicated list of DISTINCT real competitor company
names (not the company itself, not generic terms like "alternatives" or
listicle site names like "G2"/"Capterra" unless the competitor's own name
also appears). For each, give a one-sentence reason drawn from the search
results for why it's considered a competitor.

Return ONLY a JSON array, e.g.:
[{"name": "Acme Corp", "reason": "Frequently compared as a direct alternative for the same use case"}]
If nothing usable is present, return []."""


class CompetitorDiscoveryAgent:
    async def discover(self, company: str, max_suggestions: int = 8) -> List[CompetitorSuggestion]:
        raw_results = await call_tool("discover_competitors_search", company=company)
        results = raw_results or []
        if not results:
            return []

        results_txt = "\n".join(f"- {r.get('title', '')}: {r.get('snippet', '')} ({r.get('url', '')})" for r in results)
        user_prompt = f"Company: {company}\n\nSearch results:\n{results_txt}"
        response = await call_llm(DISCOVERY_SYSTEM_PROMPT, user_prompt, max_tokens=1000)
        try:
            items = extract_json(response)
        except Exception:
            return []

        suggestions: List[CompetitorSuggestion] = []
        seen = {company.strip().lower()}
        for item in items:
            name = (item.get("name") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            suggestions.append(CompetitorSuggestion(name=name, reason=item.get("reason", "")))
            if len(suggestions) >= max_suggestions:
                break
        return suggestions
