"""
Ad-hoc social listening scan: given up to 5 competitor names, searches
Twitter/X, LinkedIn, and Reddit via SerpAPI and returns a scorecard per
competitor (tone/voice, pricing clarity, hiring signal, social momentum,
content velocity). Separate from /briefs/run - this is for quick,
on-demand lookups rather than the scheduled knowledge-graph pipeline.
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.social_listening_agent import SocialListeningAgent
from app.models.schemas import SocialScorecard

router = APIRouter(prefix="/social", tags=["social"])
agent = SocialListeningAgent()


class SocialScanRequest(BaseModel):
    competitors: List[str] = Field(..., min_length=1, max_length=5)
    platforms: Optional[List[str]] = None  # subset of ["twitter", "linkedin", "reddit"]; omit for all three


@router.post("/scan", response_model=List[SocialScorecard])
async def scan_social(req: SocialScanRequest):
    names = [c.strip() for c in req.competitors if c.strip()]
    if not names:
        raise HTTPException(400, "Provide at least one competitor name.")
    if len(names) > 5:
        raise HTTPException(400, "Up to 5 competitors per scan.")
    return await agent.scan_many(names, req.platforms)
