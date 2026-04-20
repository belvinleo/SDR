"""Tavily wrapper — real-time news and signal grounding."""
import os, structlog
from tavily import AsyncTavilyClient
from .base import ToolError

log = structlog.get_logger()
_client = AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


async def search(query: str, max_results: int = 4) -> list[dict]:
    """
    Search the web for real-time signals.
    Returns list of {"title": str, "url": str, "content": str}
    """
    try:
        response = await _client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
        )
        results = response.get("results", [])
        log.info("tavily.search", query=query[:60], results=len(results))
        return [
            {"title": r.get("title"), "url": r.get("url"), "content": r.get("content", "")}
            for r in results
        ]
    except Exception as e:
        log.error("tavily.search_failed", error=str(e))
        return []
