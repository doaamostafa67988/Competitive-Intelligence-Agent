"""
Persistence + retrieval for briefs and week-over-week graph snapshots.
Also handles posting the finished brief to Telegram via the MCP tool.
"""
from __future__ import annotations
import json
import logging
from sqlalchemy import select
from app.db.postgres_client import AsyncSessionLocal, BriefRecord
from app.models.schemas import CompetitiveBrief
from app.mcp.mcp_client import call_tool
from app.services.guardrails import redact_pii


async def save_brief(brief: CompetitiveBrief) -> None:
    async with AsyncSessionLocal() as session:
        record = BriefRecord(
            id=brief.id,
            run_date=brief.run_date,
            competitors_covered=brief.competitors_covered,
            executive_summary=brief.executive_summary,
            sections_json=[s.model_dump() for s in brief.sections],
            change_log_json=[c.model_dump() for c in brief.change_log],
            unconfirmed_claims_json=brief.unconfirmed_claims,
            change_log_summary=brief.change_log_summary,
        )
        session.add(record)
        await session.commit()


async def list_briefs(limit: int = 20):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BriefRecord).order_by(BriefRecord.run_date.desc()).limit(limit)
        )
        return result.scalars().all()


async def get_brief(brief_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BriefRecord).where(BriefRecord.id == brief_id))
        return result.scalar_one_or_none()


def render_markdown(brief: CompetitiveBrief) -> str:
    lines = [f"# Weekly Competitive Brief — {brief.run_date.strftime('%Y-%m-%d')}", "", brief.executive_summary, ""]
    for section in brief.sections:
        lines.append(f"## {section.heading}")
        lines.append(section.body_markdown)
        if section.cited_source_urls:
            lines.append("")
            lines.append("Sources: " + ", ".join(section.cited_source_urls))
        lines.append("")
    if brief.change_log:
        lines.append("## What's New This Week")
        if brief.change_log_summary:
            lines.append(f"_{brief.change_log_summary}_")
            lines.append("")
        for entry in brief.change_log:
            lines.append(f"- [{entry.change_type.upper()}] {entry.competitor}: {entry.description}")
        lines.append("")
    if brief.unconfirmed_claims:
        lines.append("## Unconfirmed (flagged, not asserted as fact)")
        for c in brief.unconfirmed_claims:
            lines.append(f"- {c}")
    return "\n".join(lines)


logger = logging.getLogger("brief_service")


async def publish_to_telegram(brief: CompetitiveBrief) -> dict:
    markdown = redact_pii(render_markdown(brief), step="brief_service.publish_to_telegram")
    result = await call_tool("post_telegram_digest", markdown_text=markdown)
    if not result or not result.get("ok"):
        reason = (result or {}).get("reason", "no response from MCP tool")
        logger.warning("Telegram publish failed for brief %s: %s", brief.id, reason)
    return result or {"ok": False, "reason": "no response from MCP tool"}
