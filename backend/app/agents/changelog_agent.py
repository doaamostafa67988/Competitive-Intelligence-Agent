"""
Change-Log Agent
------------------
Role: diffs this week's Neo4j graph snapshot against last week's stored
snapshot (kept in Postgres as JSON) and produces a "What's New" section
appended to the brief. This is what makes the digest additive rather than a
full re-read every week.

diff_against_snapshot() stays deterministic on purpose - no LLM - because an
LLM inferring "what changed" from scratch could hallucinate a change that
never happened, which is the worst place for that to happen in a section
literally called the change log. summarize_relevant_changes() is a separate,
optional LLM pass *on top of* that already-correct diff: it only narrates
and filters entries down to what the user's tracked_topics say they care
about, never invents new entries.
"""
from __future__ import annotations
from typing import List, Dict, Any
from app.agents.llm import call_llm, extract_json
from app.db.neo4j_client import get_neo4j_client
from app.models.schemas import ChangeLogEntry
from app.services.guardrails import check_output_json_schema

SUMMARY_SYSTEM_PROMPT = """You summarize a week's raw knowledge-graph change
entries (facts that were newly added, modified, or removed about tracked
competitors), filtered down to what's relevant to the user's watched topics.

You are given a numbered list of change entries and a list of watched
topics. Return ONLY a JSON object:
{
  "summary": "2-4 sentence narrative covering only the changes relevant to the watched topics - empty string if none are relevant",
  "relevant_indices": [list of the integer indices (from the numbered input list) of entries you used in the summary]
}
Do not describe or reference any entry that isn't genuinely related to at
least one watched topic. If no entries relate to the topics, or no topics
are given, return {"summary": "", "relevant_indices": []}. Never invent an
entry that wasn't in the input list."""


def _triple_key(t: Dict[str, Any]) -> str:
    return f"{t['from_key']}::{t['rel_type']}::{t['to_key']}"


class ChangeLogAgent:
    def __init__(self):
        self.neo4j = get_neo4j_client()

    def diff_against_snapshot(self, previous_snapshot: List[Dict[str, Any]] | None) -> List[ChangeLogEntry]:
        current = self.neo4j.snapshot()
        previous = previous_snapshot or []

        prev_by_key = {_triple_key(t): t for t in previous}
        curr_by_key = {_triple_key(t): t for t in current}

        entries: List[ChangeLogEntry] = []

        for key, triple in curr_by_key.items():
            competitor = triple["from_key"].split("::")[0]
            if key not in prev_by_key:
                entries.append(
                    ChangeLogEntry(
                        competitor=competitor,
                        change_type="new",
                        description=f"{triple['from_key']} --{triple['rel_type']}--> {triple['to_key']}",
                        new_value=str(triple.get("props", {})),
                    )
                )
            elif triple.get("props") != prev_by_key[key].get("props"):
                entries.append(
                    ChangeLogEntry(
                        competitor=competitor,
                        change_type="modified",
                        description=f"{triple['from_key']} --{triple['rel_type']}--> {triple['to_key']}",
                        previous_value=str(prev_by_key[key].get("props", {})),
                        new_value=str(triple.get("props", {})),
                    )
                )

        for key, triple in prev_by_key.items():
            if key not in curr_by_key:
                competitor = triple["from_key"].split("::")[0]
                entries.append(
                    ChangeLogEntry(
                        competitor=competitor,
                        change_type="removed",
                        description=f"{triple['from_key']} --{triple['rel_type']}--> {triple['to_key']}",
                        previous_value=str(triple.get("props", {})),
                    )
                )

        return entries

    def current_snapshot(self) -> List[Dict[str, Any]]:
        return self.neo4j.snapshot()

    async def summarize_relevant_changes(self, entries: List[ChangeLogEntry], topics: List[str]) -> tuple[str, list[int]]:
        """Narrate + filter `entries` down to the ones relevant to `topics`.
        Returns ("", []) with no LLM call at all if either list is empty -
        an empty topics list means the user hasn't configured any watched
        topics yet (see api/routes_topics.py), so there's nothing to filter
        for and the raw diff list in the brief speaks for itself."""
        if not topics or not entries:
            return "", []

        payload = "\n".join(
            f"{i}. [{e.change_type}] {e.competitor}: {e.description}" for i, e in enumerate(entries)
        )
        user_prompt = f"Watched topics: {', '.join(topics)}\n\nChange entries:\n{payload}"
        response = await call_llm(SUMMARY_SYSTEM_PROMPT, user_prompt, step="changelog.summarize")
        try:
            data = extract_json(response)
        except Exception:
            return "", []
        # Output guardrail: malformed response -> no summary, never a
        # half-built one written into the brief.
        if not check_output_json_schema(data, {"summary"}, step="changelog.summarize"):
            return "", []

        summary = data.get("summary", "") or ""
        raw_indices = data.get("relevant_indices", [])
        # Enforce "never invent an entry" from the prompt in code, not just
        # instruction: drop any index the LLM returned that isn't actually
        # in range, rather than trusting it blindly.
        valid_indices = [i for i in raw_indices if isinstance(i, int) and 0 <= i < len(entries)]
        return summary, valid_indices
