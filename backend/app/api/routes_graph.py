"""
Read-only endpoints exposing the knowledge graph for the interactive
visualization (bonus feature) and ad-hoc GraphRAG queries from the frontends.
"""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from app.db.neo4j_client import get_neo4j_client

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/snapshot")
async def snapshot():
    """Full graph as a flat edge list — used by the interactive graph viz."""
    neo4j = get_neo4j_client()
    return neo4j.snapshot()


class CypherQuery(BaseModel):
    cypher: str
    params: dict = {}


@router.post("/query")
async def run_cypher(q: CypherQuery):
    """Ad-hoc READ-ONLY Cypher for power users / the dashboard's 'ask the graph' box.
    NOTE: for production, validate/sandbox this (e.g. reject non-MATCH/RETURN
    statements) before exposing it publicly."""
    neo4j = get_neo4j_client()
    return neo4j.query_relationship_question(q.cypher, q.params)


@router.get("/repeat-price-changers")
async def repeat_price_changers(since: str, n: int = 2):
    neo4j = get_neo4j_client()
    return neo4j.competitors_who_changed_price_n_times(since, n)
