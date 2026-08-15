"""
Thin wrapper around the Neo4j driver for the competitor knowledge graph.

Graph model:
  (:Competitor {name})
  (:Product {key, name})
  (:PricePoint {key, plan, amount, currency, date})
  (:Announcement {key, title, date, url, sentiment})
  (:JobPosting {key, title, team, date, url})

  (Competitor)-[:OFFERS]->(Product)
  (Product)-[:PRICED_AT]->(PricePoint)
  (Competitor)-[:RAISED_PRICE_ON|LOWERED_PRICE_ON]->(PricePoint)
  (Competitor)-[:ANNOUNCED]->(Announcement)
  (Competitor)-[:POSTED_ROLE]->(JobPosting)
"""
from __future__ import annotations
from typing import List, Dict, Any
from neo4j import GraphDatabase, Driver
from app.config import get_settings
from app.models.schemas import GraphEntity, GraphRelationship

settings = get_settings()


class Neo4jClient:
    def __init__(self):
        self._driver: Driver = GraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

    def close(self):
        self._driver.close()

    def ensure_constraints(self):
        stmts = [
            "CREATE CONSTRAINT competitor_key IF NOT EXISTS FOR (n:Competitor) REQUIRE n.key IS UNIQUE",
            "CREATE CONSTRAINT product_key IF NOT EXISTS FOR (n:Product) REQUIRE n.key IS UNIQUE",
            "CREATE CONSTRAINT priceP_key IF NOT EXISTS FOR (n:PricePoint) REQUIRE n.key IS UNIQUE",
            "CREATE CONSTRAINT announce_key IF NOT EXISTS FOR (n:Announcement) REQUIRE n.key IS UNIQUE",
            "CREATE CONSTRAINT job_key IF NOT EXISTS FOR (n:JobPosting) REQUIRE n.key IS UNIQUE",
        ]
        with self._driver.session() as session:
            for stmt in stmts:
                session.run(stmt)

    def upsert_entity(self, entity: GraphEntity):
        query = f"""
        MERGE (n:{entity.label} {{key: $key}})
        SET n += $props
        """
        with self._driver.session() as session:
            session.run(query, key=entity.key, props=entity.properties)

    def set_competitor_tracked(self, key: str, tracked: bool):
        """Untrack (tracked=false) rather than delete the node outright, so
        historical PricePoint/Announcement/JobPosting relationships tied to
        this competitor's past briefs aren't lost."""
        query = "MATCH (c:Competitor {key: $key}) SET c.tracked = $tracked"
        with self._driver.session() as session:
            session.run(query, key=key, tracked=tracked)

    def upsert_relationship(self, rel: GraphRelationship):
        query = f"""
        MATCH (a {{key: $from_key}})
        MATCH (b {{key: $to_key}})
        MERGE (a)-[r:{rel.rel_type}]->(b)
        SET r += $props
        """
        with self._driver.session() as session:
            session.run(query, from_key=rel.from_key, to_key=rel.to_key, props=rel.properties)

    def apply_graph_update(self, entities: List[GraphEntity], relationships: List[GraphRelationship]):
        for e in entities:
            self.upsert_entity(e)
        for r in relationships:
            self.upsert_relationship(r)

    def snapshot(self) -> List[Dict[str, Any]]:
        """Return a flat list of (from, rel_type, to, props) triples for diffing week over week."""
        query = """
        MATCH (a)-[r]->(b)
        RETURN a.key AS from_key, type(r) AS rel_type, b.key AS to_key, properties(r) AS props
        """
        with self._driver.session() as session:
            result = session.run(query)
            return [dict(record) for record in result]

    def query_relationship_question(self, cypher: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        """Run an arbitrary read-only Cypher query for GraphRAG relationship questions."""
        with self._driver.session() as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]

    def competitors_who_changed_price_n_times(self, since_iso: str, n: int = 2) -> List[Dict[str, Any]]:
        cypher = """
        MATCH (c:Competitor)-[r:RAISED_PRICE_ON|LOWERED_PRICE_ON]->(:PricePoint)
        WHERE r.date >= $since
        WITH c.name AS competitor, count(r) AS changes
        WHERE changes >= $n
        RETURN competitor, changes ORDER BY changes DESC
        """
        return self.query_relationship_question(cypher, {"since": since_iso, "n": n})


_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
