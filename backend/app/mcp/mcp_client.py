"""
MCP client used by the Research Agent to call tools hosted in mcp_server.py.
Wraps the async MCP session so agent code can call tools like plain async
functions.
"""
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastmcp import Client
from fastmcp.exceptions import ToolError
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("mcp_client")


@asynccontextmanager
async def mcp_session():
    async with Client(settings.MCP_SERVER_URL) as client:
        yield client


async def call_tool(tool_name: str, **kwargs):
    """
    Calls an MCP tool and returns its result.

    Resilient by design: if the tool itself errors out (bad API key, rate
    limit, network blip, etc.) this logs the failure and returns None
    instead of raising, so a single failing source doesn't take down the
    whole LangGraph pipeline. Callers already treat falsy results as
    "nothing found" (e.g. `news_results or []`), so this is safe to do
    broadly rather than tool-by-tool.
    """
    try:
        async with mcp_session() as client:
            result = await client.call_tool(tool_name, kwargs)
    except ToolError as e:
        logger.warning("MCP tool '%s' failed, skipping this source: %s", tool_name, e)
        return None
    except Exception as e:
        logger.warning("MCP tool '%s' failed unexpectedly, skipping this source: %s", tool_name, e)
        return None

    # NOTE: fastmcp 2.11.3 has a bug where CallToolResult.data returns
    # empty `Root()` model instances instead of plain dicts/lists for
    # tools annotated to return `dict`/`list[dict]` (untyped/loosely
    # typed JSON). result.structured_content is unaffected and always
    # holds the real, correctly-shaped JSON, so prefer it whenever
    # result.data doesn't look usable.
    data = getattr(result, "data", None)
    looks_broken = (isinstance(data, list) and any(not isinstance(i, dict) for i in data)) or (
        data is not None and not isinstance(data, (list, dict, str, int, float, bool)) and not hasattr(data, "get")
    )

    if looks_broken:
        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict) and "result" in structured:
            return structured["result"]
        if isinstance(structured, dict):
            return structured

    return data if data is not None else result
