"""Gaming Collector orchestration layer.

Connects official source selection, source fetching, and hotspot analysis:
    SourceSelector -> GameSourceFetcher -> GamingPipeline

The collector turns successfully fetched items into pipeline article inputs
and returns hotspot results with source/article counts. Failures in one
source never block the remaining sources.

Usage:
    python gaming_collector.py --game-id GMHY-YS --event-type version_update
    python gaming_collector.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlsplit

from game_source_fetcher import GameSourceFetcher
from gaming_event_store import DEFAULT_EVENT_STORE_PATH, GamingEventStore
from gaming_pipeline import GamingPipeline
from source_selector import SourceSelector


_GENERIC_PUBLISHER_HOSTS = {
    "qq.com", "www.qq.com", "game.qq.com", "163.com", "www.163.com",
    "warnerbros.com", "www.warnerbros.com", "ea.com", "www.ea.com",
}


class GamingCollector:
    def __init__(
        self, selector=None, fetcher=None, pipeline=None, registry_path=None,
        event_store=None, event_store_path=DEFAULT_EVENT_STORE_PATH,
    ):
        self.selector = selector if selector is not None else SourceSelector(registry_path)
        self.fetcher = fetcher if fetcher is not None else GameSourceFetcher(self.selector, registry_path)
        self.pipeline = pipeline if pipeline is not None else GamingPipeline(registry_path)
        self.event_store_path = event_store_path
        if event_store is not None:
            self.event_store = event_store
        else:
            try:
                self.event_store = GamingEventStore.load(event_store_path)
            except (OSError, ValueError, TypeError):
                # A broken v2 cache cannot stop the legacy collection path.
                self.event_store = GamingEventStore()

    def collect_game_events(self, game_id, event_type=None) -> dict:
        game_id = game_id or ""
        selection = self.selector.select(game_id, event_type or "")
        sources = selection.get("sources", [])

        try:
            fetched = self.fetcher.fetch_sources(sources)
        except Exception:
            fetched = []

        articles = []
        for fetched_item in fetched:
            if fetched_item.get("fetch_status") != "success":
                continue
            item = dict(fetched_item)
            item.setdefault("summary", item.get("content") or "")
            item.setdefault("id", item.get("article_id") or item.get("url") or "")
            item["source_game_id"] = game_id
            context = self._safe_source_context(item, game_id)
            item["source_context_safe"] = context is not None
            if context:
                item.update(context)
            articles.append(item)

        try:
            hotspots = self.pipeline.process_articles(articles)
        except Exception:
            hotspots = []

        normalized = {"events": [], "pending": []}
        store_stats = None
        try:
            normalized = self.pipeline.normalize_articles(articles)
            store_stats = self.event_store.ingest(normalized)
            if self.event_store_path is not None:
                self.event_store.save(self.event_store_path)
        except Exception:
            # The v2 parallel output must never change the legacy Aggregator result.
            normalized = {"events": [], "pending": []}
            store_stats = None

        return {
            "game_id": game_id,
            "sources_checked": len(sources),
            "articles_found": len(articles),
            "hotspots": hotspots,
            "events": normalized["events"],
            "pending": normalized["pending"],
            "event_store_stats": store_stats,
        }

    def _safe_source_context(self, article, game_id) -> dict | None:
        """Use configured game identity only for a verified, game-specific article."""
        if not article.get("source_is_article"):
            return None
        host = (urlsplit(article.get("source_url") or article.get("url") or "").hostname or "").casefold()
        if host in _GENERIC_PUBLISHER_HOSTS:
            return None
        entry = next(
            (item for item in self.pipeline.resolver.games if item.get("game_id") == game_id),
            None,
        )
        if not entry:
            return None
        name = entry.get("name_cn") or entry.get("name_en")
        if not name:
            return None
        return {
            "game_id": game_id,
            "game_name": name,
            "platforms": list(entry.get("platforms") or []),
            "display_group": entry.get("display_group"),
        }


def collect_game_events(game_id, event_type=None, registry_path=None) -> dict:
    return GamingCollector(registry_path=registry_path).collect_game_events(game_id, event_type)


class _FakeSelector:
    def __init__(self, sources_by_game):
        self.sources_by_game = sources_by_game
        self.last_call = None

    def select(self, game_id, event_type):
        self.last_call = (game_id, event_type)
        return {
            "game_id": game_id,
            "event_type": event_type,
            "sources": self.sources_by_game.get(game_id, []),
        }


class _FakeFetcher:
    def __init__(self, responses):
        self.responses = responses
        self.last_sources = None

    def fetch_sources(self, sources):
        self.last_sources = list(sources)
        results = []
        for source in sources:
            result = self.responses.get(source.get("url"))
            if result is None:
                result = {
                    "title": "",
                    "url": source.get("url") or "",
                    "source_name": source.get("source_name") or "",
                    "published": "",
                    "content": "",
                    "fetch_status": "fail",
                }
            results.append(result)
        return results


class _RecordingPipeline(GamingPipeline):
    def __init__(self):
        super().__init__()
        self.received = None

    def process_articles(self, articles):
        self.received = articles
        return super().process_articles(articles)


def run_selftest() -> int:
    all_ok = True

    rss_source = {
        "source_name": "测试RSS",
        "source_type": "RSS",
        "url": "https://example.com/feed",
        "priority": 100,
        "fetch_method": "RSS",
    }
    rss_article = {
        "title": "绝区零2.8版本前瞻特别节目",
        "url": "https://example.com/feed/post/1",
        "source_name": "测试RSS",
        "published": "2026-08-09 10:00",
        "content": "绝区零2.8版本前瞻特别节目将于近期播出。",
        "fetch_status": "success",
    }

    selector = _FakeSelector({"GMHY-YS": [rss_source]})
    fetcher = _FakeFetcher({"https://example.com/feed": rss_article})
    pipeline = _RecordingPipeline()
    collector = GamingCollector(
        selector=selector, fetcher=fetcher, pipeline=pipeline,
        event_store=GamingEventStore(), event_store_path=None,
    )
    result = collector.collect_game_events("GMHY-YS", "version_update")

    expected_article = {
        "title": "绝区零2.8版本前瞻特别节目",
        "url": "https://example.com/feed/post/1",
        "source_name": "测试RSS",
        "published": "2026-08-09 10:00",
        "content": "绝区零2.8版本前瞻特别节目将于近期播出。",
        "fetch_status": "success",
        "summary": "绝区零2.8版本前瞻特别节目将于近期播出。",
        "id": "https://example.com/feed/post/1",
        "source_game_id": "GMHY-YS",
        "source_context_safe": False,
    }
    ok = (
        result["sources_checked"] == 1
        and result["articles_found"] == 1
        and len(result["hotspots"]) == 1
        and result["hotspots"][0]["game_name"] == "绝区零"
        and result["hotspots"][0]["hotspot_score"] == 70
        and fetcher.last_sources == [rss_source]
        and pipeline.received == [expected_article]
        and selector.last_call == ("GMHY-YS", "version_update")
    )
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 单游戏 RSS mock: {json.dumps(result, ensure_ascii=False)}")

    html_source = {
        "source_name": "失败HTML",
        "source_type": "官网",
        "url": "https://example.com/broken",
        "priority": 90,
        "fetch_method": "HTML",
    }
    api_source = {
        "source_name": "测试API",
        "source_type": "API",
        "url": "https://example.com/api",
        "priority": 80,
        "fetch_method": "API",
    }
    fail_result = {
        "title": "",
        "url": html_source["url"],
        "source_name": html_source["source_name"],
        "published": "",
        "content": "",
        "fetch_status": "fail",
    }
    unsupported_result = {
        "title": "",
        "url": api_source["url"],
        "source_name": api_source["source_name"],
        "published": "",
        "content": "",
        "fetch_status": "unsupported",
    }

    selector = _FakeSelector({"GMHY-ZZ": [rss_source, html_source, api_source]})
    fetcher = _FakeFetcher(
        {
            "https://example.com/feed": rss_article,
            "https://example.com/broken": fail_result,
            "https://example.com/api": unsupported_result,
        }
    )
    collector = GamingCollector(
        selector=selector, fetcher=fetcher, pipeline=_RecordingPipeline(),
        event_store=GamingEventStore(), event_store_path=None,
    )
    result = collector.collect_game_events("GMHY-ZZ", "version_update")

    ok = (
        result["sources_checked"] == 3
        and result["articles_found"] == 1
        and len(result["hotspots"]) == 1
        and result["hotspots"][0]["game_name"] == "绝区零"
    )
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 多来源失败隔离: {json.dumps(result, ensure_ascii=False)}")

    selector = _FakeSelector({})
    collector = GamingCollector(
        selector=selector, fetcher=fetcher, pipeline=_RecordingPipeline(),
        event_store=GamingEventStore(), event_store_path=None,
    )
    result = collector.collect_game_events("GAME-NOT-EXIST", "version_update")

    ok = (
        result["game_id"] == "GAME-NOT-EXIST"
        and result["sources_checked"] == 0
        and result["articles_found"] == 0
        and result["hotspots"] == []
    )
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 不存在游戏: {json.dumps(result, ensure_ascii=False)}")

    return 0 if all_ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gaming Collector 统一入口")
    parser.add_argument("--game-id", help="游戏 ID")
    parser.add_argument("--event-type", help="事件类型")
    parser.add_argument("--registry", help="自定义注册表 JSON 路径")
    parser.add_argument("--selftest", action="store_true", help="运行内置 mock 验证")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()
    if not args.game_id:
        parser.error("需要 --game-id 或 --selftest")

    result = collect_game_events(args.game_id, args.event_type, args.registry)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
