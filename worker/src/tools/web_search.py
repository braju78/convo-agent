"""Web search tool. Phase 1: stub. Phase 2: real Tavily integration."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from agent_utils.core.tools.decorators import io_tool

from worker.src.dtos import SearchResult, Source

_TAVILY_URL = "https://api.tavily.com/search"


@io_tool(
    description=(
        "Search the web for current information. Use for recent events, "
        "time-sensitive facts, or anything the model may not know. "
        "Returns a list of results with URL, title, and snippet."
    ),
)
async def web_search(query: str, max_results: int = 5) -> SearchResult:
    """Search the web via Tavily. Falls back to a stub if TAVILY_API_KEY is unset."""
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        return SearchResult(
            query=query,
            results=[
                Source(
                    url="https://example.invalid/stub",
                    title=f"[STUB] search for: {query}",
                    snippet=(
                        "TAVILY_API_KEY not set. This is a Phase 1 stub result. "
                        "Set the env var to enable real search."
                    ),
                    published_at=datetime.now(timezone.utc),
                )
            ],
        )

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            _TAVILY_URL,
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max(1, min(max_results, 10)),
                "search_depth": "basic",
            },
        )
        r.raise_for_status()
        data = r.json()

    return SearchResult(
        query=query,
        results=[
            Source(
                url=item.get("url", ""),
                title=item.get("title", ""),
                snippet=item.get("content"),
                published_at=None,
            )
            for item in data.get("results", [])
        ],
    )
