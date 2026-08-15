"""
CRUD-ish endpoints for the set of tracked competitors and their source URLs.
For simplicity this stores config in-memory/Neo4j Competitor nodes rather
than a separate table; swap for a Postgres table if you need richer config.
"""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from app.db.neo4j_client import get_neo4j_client
from app.agents.competitor_discovery_agent import CompetitorDiscoveryAgent
from app.models.schemas import CompetitorSuggestion

router = APIRouter(prefix="/competitors", tags=["competitors"])
discovery_agent = CompetitorDiscoveryAgent()


class CompetitorConfig(BaseModel):
    name: str
    pricing_url: str | None = None
    careers_url: str | None = None


class DiscoverRequest(BaseModel):
    company: str


@router.post("/discover", response_model=list[CompetitorSuggestion])
async def discover_competitors(req: DiscoverRequest):
    """Given the user's own company name, suggest real competitors found on
    the web instead of requiring them to be typed in by hand. Suggestions
    are NOT auto-added — call POST /competitors for each one the user picks."""
    return await discovery_agent.discover(req.company.strip())


@router.get("")
async def list_competitors():
    neo4j = get_neo4j_client()
    # Only return competitors explicitly added/confirmed via this form.
    # The graph-builder agent auto-creates Competitor nodes for whatever
    # names the LLM extracts from news text while processing OTHER
    # competitors' claims — those are noise for configuration purposes
    # (and, since the frontend feeds this list back in as pipeline
    # targets, letting them leak in here silently grows every run's
    # LLM token usage). `tracked: true` is only ever set below.
    rows = neo4j.query_relationship_question(
        "MATCH (c:Competitor) WHERE c.tracked = true "
        "RETURN c.key AS name, c.pricing_url AS pricing_url, c.careers_url AS careers_url"
    )
    return rows


@router.post("")
async def upsert_competitor(config: CompetitorConfig):
    neo4j = get_neo4j_client()
    from app.models.schemas import GraphEntity
    neo4j.upsert_entity(
        GraphEntity(
            label="Competitor",
            key=config.name,
            properties={
                "name": config.name,
                "pricing_url": config.pricing_url,
                "careers_url": config.careers_url,
                "tracked": True,
            },
        )
    )
    return {"ok": True, "competitor": config.name}


@router.delete("/{name}")
async def remove_competitor(name: str):
    """Stop tracking a competitor (removes it from the config list and from
    future pipeline runs). Historical graph data for it is kept intact."""
    neo4j = get_neo4j_client()
    neo4j.set_competitor_tracked(name, False)
    return {"ok": True, "competitor": name, "tracked": False}
