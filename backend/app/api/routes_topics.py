"""
CRUD for user-defined tracked topics - replaces the hardcoded 3-theme list
that used to live in analyst_agent.py. Consumed by the Analyst Agent
(thematic vector search) and the Change-Log Agent (topic-filtered summary).
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.postgres_client import add_topic, list_topics, delete_topic
from app.services.guardrails import check_contextual_compliance, check_input_text

router = APIRouter(prefix="/topics", tags=["topics"])

MAX_TOPIC_LENGTH = 120


class TopicRequest(BaseModel):
    topic: str


@router.get("")
async def get_topics():
    return await list_topics()


@router.post("")
async def create_topic(req: TopicRequest):
    topic = req.topic.strip()
    # Input guardrails: same bar as any other free text reaching an LLM
    # prompt (this feeds the Analyst/Change-Log prompts every pipeline run).
    if not check_contextual_compliance(topic, min_length=2) or len(topic) > MAX_TOPIC_LENGTH:
        raise HTTPException(400, f"Topic must be between 2 and {MAX_TOPIC_LENGTH} characters.")
    check_input_text(topic, source="tracked_topic_input")
    return await add_topic(topic)


@router.delete("/{topic_id}")
async def remove_topic(topic_id: str):
    await delete_topic(topic_id)
    return {"ok": True}
