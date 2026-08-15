"""
Alerting Agent (bonus feature)
--------------------------------
Runs on a short poll cycle (settings.ALERT_POLL_MINUTES) independent of the
weekly pipeline. Uses a lightweight version of the Research Agent's news
search to catch high-severity events (funding rounds, layoffs, major
launches) and pings Telegram immediately rather than waiting for the weekly
digest.
"""
from __future__ import annotations
import uuid
from app.agents.llm import call_llm, extract_json
from app.mcp.mcp_client import call_tool
from app.models.schemas import AlertEvent

ALERT_SYSTEM_PROMPT = """You monitor breaking competitor news for a SaaS
company's leadership team. Given a batch of recent headlines/snippets for a
competitor, decide if any represent a MAJOR move worth an immediate alert
(funding round, acquisition, major outage, executive departure, major price
change, security incident). Ignore routine content marketing.
Return ONLY a JSON array of {headline, detail, source_url, severity
(low/medium/high)}. Return [] if nothing qualifies."""


async def check_for_alerts(competitor: str) -> list[AlertEvent]:
    news = await call_tool("web_news_search", query=f"{competitor} funding OR acquisition OR layoffs OR outage", max_results=10)
    if not news:
        return []
    payload = "\n".join(f"- {n.get('title')} | {n.get('url')} | {n.get('snippet')}" for n in news)
    response = await call_llm(ALERT_SYSTEM_PROMPT, f"Competitor: {competitor}\n\n{payload}")
    try:
        items = extract_json(response)
    except Exception:
        return []

    alerts = [
        AlertEvent(
            id=str(uuid.uuid4()),
            competitor=competitor,
            severity=item.get("severity", "low"),
            headline=item.get("headline", ""),
            detail=item.get("detail", ""),
            source_url=item.get("source_url", ""),
        )
        for item in items
    ]

    for alert in alerts:
        if alert.severity in ("medium", "high"):
            await call_tool(
                "post_telegram_digest",
                markdown_text=f":rotating_light: *{alert.severity.upper()} ALERT — {alert.competitor}*\n{alert.headline}\n{alert.detail}\n{alert.source_url}",
            )
    return alerts
