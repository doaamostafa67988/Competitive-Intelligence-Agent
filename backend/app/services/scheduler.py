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
from app.graph.orchestrator import run_weekly_pipeline
from app.services.brief_service import save_brief, publish_to_telegram
from app.services.alerting import check_for_alerts
from app.agents.changelog_agent import ChangeLogAgent

settings = get_settings()
logger = logging.getLogger("scheduler")
scheduler = AsyncIOScheduler()

_last_snapshot_cache: list | None = None


async def _weekly_job():
    global _last_snapshot_cache
    targets = [{"name": name, "pricing_url": None, "careers_url": None} for name in settings.TRACKED_COMPETITORS]
    brief = await run_weekly_pipeline(targets, _last_snapshot_cache)
    await save_brief(brief)
    await publish_to_telegram(brief)
    _last_snapshot_cache = ChangeLogAgent().current_snapshot()
    logger.info("Weekly competitive brief generated: %s", brief.id)


async def _alert_job():
    for competitor in settings.TRACKED_COMPETITORS:
        await check_for_alerts(competitor)


def start_scheduler():
    scheduler.add_job(_weekly_job, CronTrigger.from_crontab(settings.WEEKLY_RUN_CRON), id="weekly_pipeline", replace_existing=True)
    scheduler.add_job(_alert_job, IntervalTrigger(minutes=settings.ALERT_POLL_MINUTES), id="alert_poll", replace_existing=True)
    scheduler.start()
