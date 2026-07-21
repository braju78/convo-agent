"""Server-side citation validation — drop URLs the LLM invented."""

from __future__ import annotations

from types import SimpleNamespace

from worker.src.dtos import Source
from worker.src.workflow import _collect_search_urls, _validate_sources


def _call(tool_name: str, results: list[dict]) -> SimpleNamespace:
    """Mimic a ToolCallRecord — SDK returns Pydantic; we accept SimpleNamespace."""
    return SimpleNamespace(tool_name=tool_name, result={"results": results})


class TestCollectSearchUrls:
    def test_collects_urls_from_web_search(self):
        calls = [
            _call("web_search", [
                {"url": "https://a.com", "title": "A"},
                {"url": "https://b.com", "title": "B"},
            ]),
        ]
        assert _collect_search_urls(calls) == {"https://a.com", "https://b.com"}

    def test_ignores_non_web_search_tools(self):
        calls = [
            _call("other_tool", [{"url": "https://z.com", "title": "Z"}]),
            _call("web_search", [{"url": "https://a.com", "title": "A"}]),
        ]
        assert _collect_search_urls(calls) == {"https://a.com"}

    def test_handles_empty_tool_calls(self):
        assert _collect_search_urls([]) == set()

    def test_handles_missing_results(self):
        broken = SimpleNamespace(tool_name="web_search", result=None)
        assert _collect_search_urls([broken]) == set()

    def test_dedupes_across_multiple_calls(self):
        calls = [
            _call("web_search", [{"url": "https://a.com", "title": "A"}]),
            _call("web_search", [{"url": "https://a.com", "title": "A dup"}]),
        ]
        assert _collect_search_urls(calls) == {"https://a.com"}


class TestValidateSources:
    def test_keeps_urls_in_allowed_set(self):
        proposed = [Source(url="https://a.com", title="A")]
        kept, dropped = _validate_sources(proposed, {"https://a.com"})
        assert kept == proposed
        assert dropped == []

    def test_drops_urls_not_in_allowed_set(self):
        proposed = [
            Source(url="https://a.com", title="A"),
            Source(url="https://fake.com", title="Hallucinated"),
        ]
        kept, dropped = _validate_sources(proposed, {"https://a.com"})
        assert len(kept) == 1 and kept[0].url == "https://a.com"
        assert len(dropped) == 1 and dropped[0].url == "https://fake.com"

    def test_empty_proposed_returns_empty(self):
        kept, dropped = _validate_sources([], {"https://a.com"})
        assert kept == [] and dropped == []

    def test_empty_allowed_drops_everything(self):
        proposed = [Source(url="https://a.com", title="A")]
        kept, dropped = _validate_sources(proposed, set())
        assert kept == []
        assert dropped == proposed
