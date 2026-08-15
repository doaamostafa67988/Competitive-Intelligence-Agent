"""
FastMCP server exposing the external data-gathering tools that the Research
Agent calls: web/news search, competitor career-page scraping, and Telegram
posting. Runs as its own process; the Research Agent connects to it as an
MCP client (see app/mcp/mcp_client.py).

Run standalone:  python -m app.mcp.mcp_server
"""
from __future__ import annotations
import httpx
from fastmcp import FastMCP
from app.config import get_settings

settings = get_settings()
mcp = FastMCP("competitive-intel-tools")


@mcp.tool()
async def web_news_search(query: str, max_results: int = 8) -> list[dict]:
    """Search the web/news for recent mentions of a competitor, product, or event.

    Args:
        query: search query, e.g. "Acme Corp pricing OR funding OR launch"
        max_results: max number of results to return
    Returns:
        list of {title, url, snippet, published_at}
    """
    if not settings.NEWS_API_KEY:
        return []
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "pageSize": max_results, "sortBy": "publishedAt", "apiKey": settings.NEWS_API_KEY},
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return [
            {
                "title": a.get("title"),
                "url": a.get("url"),
                "snippet": a.get("description"),
                "published_at": a.get("publishedAt"),
            }
            for a in articles
        ]


@mcp.tool()
async def fetch_pricing_page(url: str) -> dict:
    """Fetch a competitor's pricing page and return raw text content for extraction.

    Args:
        url: the pricing page URL
    Returns:
        {url, status_code, text}
    """
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "CompetitiveIntelBot/1.0"})
        return {"url": url, "status_code": resp.status_code, "text": resp.text[:20000]}


@mcp.tool()
async def scrape_career_page(company: str, careers_url: str, max_postings: int = 25) -> list[dict]:
    """Fetch a competitor's careers page to surface hiring-trend signals
    (roles opened, teams growing, geographies expanding).

    Args:
        company: competitor name
        careers_url: URL of the careers / jobs listing page
        max_postings: cap on postings returned
    Returns:
        list of {title, team, location, url}
    """
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(careers_url, headers={"User-Agent": "CompetitiveIntelBot/1.0"})
        # NOTE: real implementation should parse per-ATS (Greenhouse/Lever/Ashby) JSON APIs
        # rather than scraping HTML. This is a stub returning the raw payload for the
        # Research Agent's LLM extraction step to parse.
        return [{"company": company, "raw_snippet": resp.text[:15000], "source_url": careers_url}][:max_postings]


@mcp.tool()
async def discover_competitors_search(company: str, max_results: int = 10) -> list[dict]:
    """Search the web for who a given company's competitors/alternatives are
    (via SerpAPI), so the Competitor Discovery Agent can extract a clean
    competitor list instead of the user typing each one in by hand.

    Args:
        company: the company to find competitors for
        max_results: cap on raw search results returned
    Returns:
        list of {title, url, snippet}
    """
    if not settings.SERPAPI_KEY:
        return []
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://serpapi.com/search",
            params={
                "engine": "google",
                "q": f'"{company}" competitors OR alternatives OR "vs {company}"',
                "num": max_results,
                "api_key": settings.SERPAPI_KEY,
            },
        )
        resp.raise_for_status()
        organic = resp.json().get("organic_results", [])
        return [
            {"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
            for r in organic[:max_results]
        ]


SOCIAL_PLATFORM_SITE_FILTERS = {
    "twitter": "(site:twitter.com OR site:x.com)",
    "linkedin": "site:linkedin.com",
    "reddit": "site:reddit.com",
}


@mcp.tool()
async def social_listening_search(
    competitor: str, platforms: list[str] | None = None, max_results_per_platform: int = 8
) -> list[dict]:
    """Search Twitter/X, LinkedIn, and Reddit for recent posts/mentions of a
    competitor via SerpAPI site-restricted Google search (past-month window,
    so results reflect current social activity rather than old history).

    Args:
        competitor: competitor/company name to search for
        platforms: subset of ["twitter", "linkedin", "reddit"]; defaults to all three
        max_results_per_platform: cap on results returned per platform
    Returns:
        list of {platform, title, url, snippet, published_at}
    """
    if not settings.SERPAPI_KEY:
        return []
    targets = [p for p in (platforms or list(SOCIAL_PLATFORM_SITE_FILTERS)) if p in SOCIAL_PLATFORM_SITE_FILTERS]
    if not targets:
        return []

    results: list[dict] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for platform in targets:
            site_filter = SOCIAL_PLATFORM_SITE_FILTERS[platform]
            resp = await client.get(
                "https://serpapi.com/search",
                params={
                    "engine": "google",
                    "q": f'{site_filter} "{competitor}"',
                    "num": max_results_per_platform,
                    "tbs": "qdr:m",  # past month - keeps momentum/velocity signals fresh
                    "api_key": settings.SERPAPI_KEY,
                },
            )
            resp.raise_for_status()
            organic = resp.json().get("organic_results", [])
            for item in organic[:max_results_per_platform]:
                results.append(
                    {
                        "platform": platform,
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "published_at": item.get("date"),
                    }
                )
    return results


@mcp.tool()
async def post_telegram_digest(markdown_text: str, chat_id: str | None = None) -> dict:
    """Post the weekly competitive brief (or an alert) to the leadership Telegram chat/channel.

    Args:
        markdown_text: the formatted brief content. Telegram's MarkdownV2 is
            picky about escaping, so this is sent with parse_mode="Markdown"
            (legacy mode, more forgiving) rather than MarkdownV2.
        chat_id: Telegram chat/channel/group id override, defaults to
            settings.TELEGRAM_CHAT_ID. For a channel, this looks like
            "@my_channel_name" or a numeric id like "-1001234567890".
    Returns:
        {ok, chat_id}
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        return {"ok": False, "reason": "TELEGRAM_BOT_TOKEN not configured"}
    target = chat_id or settings.TELEGRAM_CHAT_ID
    if not target:
        return {"ok": False, "reason": "TELEGRAM_CHAT_ID not configured"}

    # Telegram caps messages at 4096 chars; split long briefs into chunks.
    chunks = [markdown_text[i : i + 4000] for i in range(0, len(markdown_text), 4000)] or [""]

    async with httpx.AsyncClient(timeout=20) as client:
        last_response = {}
        for chunk in chunks:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                # NOTE: parse_mode="Markdown" was silently failing on real briefs.
                # LLM-generated markdown (headings, [citation] brackets, URLs with
                # underscores) almost always contains unescaped/unmatched entities,
                # which Telegram's legacy Markdown parser rejects with a 400
                # "can't parse entities" error. Since Telegram already got a plain
                # "# Heading" / "## Section" style digest anyway (not true
                # MarkdownV2), sending as plain text is both simpler and reliable.
                json={"chat_id": target, "text": chunk},
            )
            last_response = resp.json()
            if not last_response.get("ok", False):
                # Surface the real reason (bad chat_id, bot not in chat/blocked,
                # bot never started by user, etc.) instead of a bare False.
                return {
                    "ok": False,
                    "chat_id": target,
                    "reason": last_response.get("description", "unknown Telegram API error"),
                }
        return {"ok": last_response.get("ok", False), "chat_id": target}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8765)
