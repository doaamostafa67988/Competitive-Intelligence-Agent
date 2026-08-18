"""
Small typed wrapper around the FastAPI backend, shared by every Streamlit page.
"""
from __future__ import annotations
import os
import httpx

API_BASE = os.getenv("BACKEND_API_URL", "http://localhost:8000/api/v1")


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=120)


def list_briefs(limit: int = 20):
    with _client() as c:
        r = c.get("/briefs", params={"limit": limit})
        r.raise_for_status()
        return r.json()


def get_brief(brief_id: str):
    with _client() as c:
        r = c.get(f"/briefs/{brief_id}")
        r.raise_for_status()
        return r.json()


def get_brief_markdown(brief_id: str):
    with _client() as c:
        r = c.get(f"/briefs/{brief_id}/markdown")
        r.raise_for_status()
        return r.json()["markdown"]


def run_pipeline(targets=None, publish_to_telegram_chat: bool = False):
    # Longer timeout than the shared client: the pipeline now runs Research
    # AND Social Listening sequentially (each with its own search + LLM
    # calls per competitor), which can comfortably exceed 120s for 5 targets.
    with httpx.Client(base_url=API_BASE, timeout=600) as c:
        r = c.post("/briefs/run", json={"targets": targets, "publish_to_telegram_chat": publish_to_telegram_chat})
        r.raise_for_status()
        return r.json()


def list_competitors():
    with _client() as c:
        r = c.get("/competitors")
        r.raise_for_status()
        return r.json()


def discover_competitors(company: str):
    with _client() as c:
        r = c.post("/competitors/discover", json={"company": company})
        r.raise_for_status()
        return r.json()


def upsert_competitor(name: str, pricing_url: str | None, careers_url: str | None):
    with _client() as c:
        r = c.post("/competitors", json={"name": name, "pricing_url": pricing_url, "careers_url": careers_url})
        r.raise_for_status()
        return r.json()


def remove_competitor(name: str):
    with _client() as c:
        r = c.delete(f"/competitors/{name}")
        r.raise_for_status()
        return r.json()


def social_scan(competitors: list[str], platforms: list[str] | None = None):
    with _client() as c:
        r = c.post("/social/scan", json={"competitors": competitors, "platforms": platforms})
        r.raise_for_status()
        return r.json()


def graph_snapshot():
    with _client() as c:
        r = c.get("/graph/snapshot")
        r.raise_for_status()
        return r.json()


def repeat_price_changers(since: str, n: int = 2):
    with _client() as c:
        r = c.get("/graph/repeat-price-changers", params={"since": since, "n": n})
        r.raise_for_status()
        return r.json()


def ask_question(question: str):
    # Longer timeout than the shared client: the Q&A agent's tool-calling
    # loop can involve several LLM round-trips (see
    # agents/llm.py::call_llm_with_tools), not a single request/response.
    with httpx.Client(base_url=API_BASE, timeout=180) as c:
        r = c.post("/qa", json={"question": question})
        r.raise_for_status()
        return r.json()


def list_topics():
    with _client() as c:
        r = c.get("/topics")
        r.raise_for_status()
        return r.json()


def add_topic(topic: str):
    with _client() as c:
        r = c.post("/topics", json={"topic": topic})
        r.raise_for_status()
        return r.json()


def remove_topic(topic_id: str):
    with _client() as c:
        r = c.delete(f"/topics/{topic_id}")
        r.raise_for_status()
        return r.json()
