"""
Graph-Builder Agent
--------------------
Role: takes CONFIRMED (and, tagged, UNCONFIRMED) claims and extracts
entities/relationships to upsert into Neo4j, e.g.
  (Competitor)-[:RAISED_PRICE_ON]->(PricePoint)-[:ON_DATE]->(...)
Only claims with status != REJECTED are considered. UNCONFIRMED claims are
still written to the graph but tagged `confirmed: false` so the Analyst
Agent and brief renderer can treat them differently.
"""
from __future__ import annotations
import logging
from datetime import date
from typing import List
from app.agents.llm import call_llm, extract_json
from app.db.neo4j_client import get_neo4j_client
from app.models.schemas import GraphEntity, GraphRelationship, GraphUpdate, VerifiedClaim, VerificationStatus
from app.services.guardrails import check_output_json_schema
from app.services.sentiment import score_sentiment

logger = logging.getLogger("graph_builder_agent")

EXTRACTION_SYSTEM_PROMPT = """You convert a verified competitive-intelligence
claim into graph entities and relationships for a Neo4j knowledge graph.

Allowed entity labels: Competitor, Product, PricePoint, Announcement, JobPosting.
Allowed relationship types: OFFERS, PRICED_AT, RAISED_PRICE_ON, LOWERED_PRICE_ON,
ANNOUNCED, POSTED_ROLE, LAUNCHED.

Return ONLY a JSON object:
{
  "entities": [{"label": "...", "key": "Competitor::Product or unique key", "properties": {...}}],
  "relationships": [{"from_key": "...", "to_key": "...", "rel_type": "...", "properties": {...}}]
}
Use natural keys like "Acme" for a Competitor, "Acme::Pro Plan" for a Product,
"Acme::Pro Plan::2026-08-11" for a PricePoint. Always include a "date"
(ISO 8601) property on PricePoint/Announcement/JobPosting nodes and
relationships where a date is implied or known; use today's date if the claim
doesn't specify one."""

# Output guardrail (also closes a Cypher-injection hole): neo4j_client.py's
# upsert_entity/upsert_relationship interpolate label/rel_type directly into
# the Cypher string (f"MERGE (n:{entity.label} ...)"). The prompt above asks
# the LLM to only use these values, but a prompt is not enforcement - this
# whitelist is checked before anything derived from the LLM response reaches
# neo4j_client, so a hallucinated or injected label/rel_type is dropped here
# instead of being interpolated into a live Cypher query.
ALLOWED_LABELS = {"Competitor", "Product", "PricePoint", "Announcement", "JobPosting"}
ALLOWED_REL_TYPES = {
    "OFFERS", "PRICED_AT", "RAISED_PRICE_ON", "LOWERED_PRICE_ON", "ANNOUNCED", "POSTED_ROLE", "LAUNCHED",
}


class GraphBuilderAgent:
    def __init__(self):
        self.neo4j = get_neo4j_client()

    async def build_and_write(self, claims: List[VerifiedClaim]) -> GraphUpdate:
        usable = [c for c in claims if c.status != VerificationStatus.REJECTED]
        entities: List[GraphEntity] = []
        relationships: List[GraphRelationship] = []
        claim_ids: List[str] = []

        for claim in usable:
            extracted = await self._extract_graph_pieces(claim)
            entities.extend(extracted[0])
            relationships.extend(extracted[1])
            claim_ids.append(claim.id)

        self.neo4j.apply_graph_update(entities, relationships)
        return GraphUpdate(entities=entities, relationships=relationships, source_claim_ids=claim_ids)

    async def _extract_graph_pieces(self, claim: VerifiedClaim):
        user_prompt = (
            f"Competitor: {claim.competitor}\n"
            f"Claim type: {claim.claim_type}\n"
            f"Claim: {claim.claim}\n"
            f"Status: {claim.status.value}\n"
            f"Today: {date.today().isoformat()}"
        )
        response = await call_llm(EXTRACTION_SYSTEM_PROMPT, user_prompt, step="graph_builder.extract")
        try:
            data = extract_json(response)
        except Exception:
            return [], []
        # Output guardrail: reject a parseable-but-malformed response (e.g.
        # missing "entities"/"relationships" keys) before we try to write
        # anything derived from it into Neo4j.
        if not check_output_json_schema(data, {"entities", "relationships"}, step="graph_builder.extract"):
            return [], []

        entities = []
        for e in data.get("entities", []):
            if e.get("label") not in ALLOWED_LABELS or not e.get("key"):
                logger.warning("graph_builder dropped entity with disallowed/missing label: %r", e.get("label"))
                continue
            props = dict(e.get("properties", {}))
            props["confirmed"] = claim.status == VerificationStatus.CONFIRMED
            props["source_claim_id"] = claim.id
            if e["label"] == "Announcement" and "sentiment" not in props:
                props["sentiment"] = await score_sentiment(claim.claim)
            entities.append(GraphEntity(label=e["label"], key=e["key"], properties=props))

        relationships = []
        for r in data.get("relationships", []):
            if r.get("rel_type") not in ALLOWED_REL_TYPES or not r.get("from_key") or not r.get("to_key"):
                logger.warning("graph_builder dropped relationship with disallowed/missing rel_type: %r", r.get("rel_type"))
                continue
            props = dict(r.get("properties", {}))
            props["confirmed"] = claim.status == VerificationStatus.CONFIRMED
            props["source_claim_id"] = claim.id
            relationships.append(
                GraphRelationship(from_key=r["from_key"], to_key=r["to_key"], rel_type=r["rel_type"], properties=props)
            )

        # Always ensure the Competitor node itself exists even if the LLM omitted it.
        # NOTE: deliberately no "tracked" property here — this node may be getting
        # auto-created just because it was mentioned in another competitor's news
        # results. Only the manual /competitors form (routes_competitors.py) sets
        # tracked=true, and `SET n += props` here never clears that flag if it's
        # already set on an existing node.
        if not any(e.label == "Competitor" and e.key == claim.competitor for e in entities):
            entities.insert(0, GraphEntity(label="Competitor", key=claim.competitor, properties={"name": claim.competitor}))

        return entities, relationships
