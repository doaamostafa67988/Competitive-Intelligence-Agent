"""
Text embedding helper used to write announcement text into Qdrant and to
embed thematic queries for the Analyst Agent's vector-search leg.
Swap the provider here without touching agent code.
"""
from __future__ import annotations
from typing import List
import voyageai
from app.config import get_settings

settings = get_settings()
_voyage_client: voyageai.AsyncClient | None = None


def _get_client() -> voyageai.AsyncClient:
    global _voyage_client
    if _voyage_client is None:
        _voyage_client = voyageai.AsyncClient()
    return _voyage_client


async def embed_text(text: str) -> List[float]:
    client = _get_client()
    result = await client.embed([text], model="voyage-3", input_type="query")
    return result.embeddings[0]


async def embed_documents(texts: List[str]) -> List[List[float]]:
    client = _get_client()
    result = await client.embed(texts, model="voyage-3", input_type="document")
    return result.embeddings
