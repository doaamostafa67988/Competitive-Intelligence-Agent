"""
Dynamic question-answering endpoint over tracked-competitor data. Unlike
routes_brief.py (fixed weekly pipeline shape), this accepts any free-text
question and lets the Q&A Agent decide which lookups answer it - see
agents/qa_agent.py for why this is separate from the Analyst Agent.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.agents.qa_agent import QAAgent

router = APIRouter(prefix="/qa", tags=["qa"])


class QuestionRequest(BaseModel):
    question: str


@router.post("")
async def ask_question(req: QuestionRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(400, "`question` must not be empty.")
    agent = QAAgent()
    result = await agent.answer(req.question.strip())
    return result.model_dump()
