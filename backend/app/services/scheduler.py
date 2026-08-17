"""
APScheduler wiring: weekly full pipeline run + frequent alert polling.
Started from app.main on FastAPI startup.
"""
from __future__ import annotations
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.config import get_settings
from app.db.neo4j_client import get_neo4j_client
from app.graph.orchestrator import run_weekly_pipeline
from app.services.brief_service import save_brief, publish_to_telegram
from app.services.alerting import check_for_alerts
from app.agents.changelog_agent import ChangeLogAgent

settings = get_settings()
logger = logging.getLogger("scheduler")
scheduler = AsyncIOScheduler()

_last_snapshot_cache: list | None = None


def _get_tracked_competitors() -> list[dict]:
    """Neo4j (tracked=true Competitor nodes) is the single source of truth
    for which competitors the scheduler runs against — same list the
    frontend's Competitors page reads/writes. settings.TRACKED_COMPETITORS
    is only used as a one-time seed fallback if Neo4j has nothing tracked
    yet (e.g. first boot before anyone has added a competitor via the UI)."""
    rows = get_neo4j_client().list_tracked_competitors()
    if rows:
        return rows
    if settings.TRACKED_COMPETITORS:
        logger.warning(
            "No tracked competitors found in Neo4j; falling back to %d from .env TRACKED_COMPETITORS",
            len(settings.TRACKED_COMPETITORS),
        )
        return [{"name": name, "pricing_url": None, "careers_url": None} for name in settings.TRACKED_COMPETITORS]
    return []


async def _weekly_job():
    global _last_snapshot_cache
    targets = _get_tracked_competitors()
    if not targets:
        logger.info("Weekly pipeline skipped: no tracked competitors")
        return
    brief = await run_weekly_pipeline(targets, _last_snapshot_cache)
    await save_brief(brief)
    await publish_to_telegram(brief)
    _last_snapshot_cache = ChangeLogAgent().current_snapshot()
    logger.info("Weekly competitive brief generated: %s", brief.id)


async def _alert_job():
    targets = _get_tracked_competitors()
    for target in targets:
        await check_for_alerts(target["name"])


def start_scheduler():
    scheduler.add_job(_weekly_job, CronTrigger.from_crontab(settings.WEEKLY_RUN_CRON), id="weekly_pipeline", replace_existing=True)
    scheduler.add_job(_alert_job, IntervalTrigger(minutes=settings.ALERT_POLL_MINUTES), id="alert_poll", replace_existing=True)
    scheduler.start()
