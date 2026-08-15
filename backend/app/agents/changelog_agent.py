"""
Change-Log Agent
------------------
Role: diffs this week's Neo4j graph snapshot against last week's stored
snapshot (kept in Postgres as JSON) and produces a "What's New" section
appended to the brief. This is what makes the digest additive rather than a
full re-read every week.
"""
from __future__ import annotations
from typing import List, Dict, Any
from app.db.neo4j_client import get_neo4j_client
from app.models.schemas import ChangeLogEntry


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
