"""
Endpoints for triggering pipeline runs and reading generated briefs.
Consumed by both the Streamlit dashboard and the Next.js frontend.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import get_settings
from app.graph.orchestrator import run_weekly_pipeline, CompetitorTarget
from app.services.brief_service import save_brief, list_briefs, get_brief, publish_to_telegram, render_markdown
from app.agents.changelog_agent import ChangeLogAgent

router = APIRouter(prefix="/briefs", tags=["briefs"])
settings = get_settings()


class RunRequest(BaseModel):
    targets: list[CompetitorTarget] | None = None
    publish_to_telegram_chat: bool = False


@router.post("/run")
async def run_pipeline(req: RunRequest):
    targets = req.targets or [
        {"name": name, "pricing_url": None, "careers_url": None} for name in settings.TRACKED_COMPETITORS
    ]
    if not targets:
        raise HTTPException(400, "No competitors configured. Pass `targets` or set TRACKED_COMPETITORS.")

    changelog_agent = ChangeLogAgent()
    previous_snapshot = changelog_agent.current_snapshot()  # pre-run snapshot for diffing

    brief = await run_weekly_pipeline(targets, previous_snapshot)
    await save_brief(brief)

    telegram_result = None
    if req.publish_to_telegram_chat:
        telegram_result = await publish_to_telegram(brief)

    return {**brief.model_dump(), "telegram_publish": telegram_result}


@router.get("")
async def get_briefs(limit: int = 20):
    records = await list_briefs(limit=limit)
    return [
        {
            "id": r.id,
            "run_date": r.run_date,
            "competitors_covered": r.competitors_covered,
            "executive_summary": r.executive_summary,
        }
        for r in records
    ]


@router.get("/{brief_id}")
async def get_brief_detail(brief_id: str):
    record = await get_brief(brief_id)
    if not record:
        raise HTTPException(404, "Brief not found")
    return {
        "id": record.id,
        "run_date": record.run_date,
        "competitors_covered": record.competitors_covered,
        "executive_summary": record.executive_summary,
        "sections": record.sections_json,
        "change_log": record.change_log_json,
        "unconfirmed_claims": record.unconfirmed_claims_json,
    }


@router.get("/{brief_id}/markdown")
async def get_brief_markdown(brief_id: str):
    record = await get_brief(brief_id)
    if not record:
        raise HTTPException(404, "Brief not found")
    from app.models.schemas import CompetitiveBrief, BriefSection, ChangeLogEntry
    brief = CompetitiveBrief(
        id=record.id,
        run_date=record.run_date,
        competitors_covered=record.competitors_covered,
        executive_summary=record.executive_summary,
        sections=[BriefSection(**s) for s in record.sections_json],
        change_log=[ChangeLogEntry(**c) for c in record.change_log_json],
        unconfirmed_claims=record.unconfirmed_claims_json,
    )
    return {"markdown": render_markdown(brief)}
