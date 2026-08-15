"""
Qdrant wrapper for semantic search over announcement / press-release / job-posting
text. Used by the Analyst Agent's GraphRAG vector-search leg (e.g. "who is
talking about AI features").
"""
from __future__ import annotations
import uuid
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from app.config import get_settings

settings = get_settings()

EMBEDDING_DIM = 1536  # matches text-embedding-3-small / voyage-3 style dims; adjust to your embedder


class VectorStore:
    def __init__(self):
        self._client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        self._collection = settings.QDRANT_COLLECTION
        self._ensure_collection()

    def _ensure_collection(self):
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=qmodels.VectorParams(size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE),
            )

    def upsert_text(self, text: str, embedding: List[float], metadata: Dict[str, Any]) -> str:
        point_id = str(uuid.uuid4())
        self._client.upsert(
            collection_name=self._collection,
            points=[qmodels.PointStruct(id=point_id, vector=embedding, payload={"text": text, **metadata})],
        )
        return point_id

    def search(self, query_embedding: List[float], top_k: int = 8, competitor: str | None = None) -> List[Dict[str, Any]]:
        query_filter = None
        if competitor:
            query_filter = qmodels.Filter(
                must=[qmodels.FieldCondition(key="competitor", match=qmodels.MatchValue(value=competitor))]
            )
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=query_embedding,
            query_filter=query_filter,
            limit=top_k,
        )
        return [{"score": h.score, **h.payload} for h in hits]


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
