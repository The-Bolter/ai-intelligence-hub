"""Official source fetch adapter for the Gaming Pipeline.

Given source configs produced by source_selector.py, fetch content according
to fetch_method: RSS uses feedparser, HTML uses requests + BeautifulSoup, and
API stays as an interface that returns unsupported until an api_endpoint is
configured. One failed source never blocks the others.

Usage:
    python game_source_fetcher.py --game-id GMHY-YS --event-type version_update
    python game_source_fetcher.py --selftest
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time

from source_selector import SourceSelector

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None


class GameSourceFetcher:
    def __init__(self, selector=None, registry_path=None, timeout=10, max_content_length=2000):
        self.timeout = timeout
        self.max_content_length = max_content_length
        self.selector = selector if selector is not None else SourceSelector(registry_path)

    def fetch_source(self, source) -> dict:
        if not isinstance(source, dict):
            return self._result({}, "fail")
        fetch_method = str(source.get("fetch_method") or "").strip().upper()
        try:
            if fetch_method == "RSS":
                return self._fetch_rss(source)
            if "HTML" in fetch_method:
                return self._fetch_html(source)
            if "API" in fetch_method:
                return self._fetch_api(source)
            return self._result(source, "unsupported")
        except Exception:
            return self._result(source, "fail")

    def fetch_sources(self, sources) -> list[dict]:
        results = []
        for source in sources or []:
            try:
                results.append(self.fetch_source(source))
            except Exception:
                results.append(self._result(source, "fail"))
        return results

    def fetch_game_sources(self, game_id, event_type=None) -> list[dict]:
        if self.selector is None:
            raise ValueError("未配置 SourceSelector，无法选择官方来源")
        selection = self.selector.select(game_id, event_type or "")
        return self.fetch_sources(selection.get("sources", []))

    def _fetch_rss(self, source) -> dict:
        if feedparser is None:
            return self._result(source, "fail")
        feed = feedparser.parse(source.get("url") or "")
        entries = getattr(feed, "entries", None) or []
        if not entries:
            return self._result(source, "fail")
        entry = entries[0]
        return self._result(
            source,
            "success",
            title=getattr(entry, "title", "") or "",
            url=getattr(entry, "link", "") or "",
            published=self._entry_published(entry),
            content=getattr(entry, "summary", "") or "",
        )

    def _fetch_html(self, source) -> dict:
        if requests is None or BeautifulSoup is None:
            return self._result(source, "fail")
        response = requests.get(source.get("url") or "", timeout=self.timeout)
        if getattr(response, "status_code", None) != 200:
            return self._result(source, "fail")
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        return self._result(source, "success", title=title, content=self._body_text(soup))

    def _fetch_api(self, source) -> dict:
        endpoint = source.get("api_endpoint")
        if not endpoint:
            return self._result(source, "unsupported")
        if requests is None:
            return self._result(source, "fail")
        response = requests.get(endpoint, timeout=self.timeout)
        if getattr(response, "status_code", None) != 200:
            return self._result(source, "fail")
        try:
            content = json.dumps(response.json(), ensure_ascii=False)
        except ValueError:
            content = response.text
        return self._result(source, "success", content=content[: self.max_content_length])

    @staticmethod
    def _entry_published(entry) -> str:
        for key in ("published_parsed", "published", "updated_parsed", "updated"):
            value = getattr(entry, key, None)
            if not value:
                continue
            if key.endswith("_parsed"):
                return time.strftime("%Y-%m-%dT%H:%M:%S", value)
            return str(value)
        return ""

    def _body_text(self, soup) -> str:
        container = soup.find("article") or soup.find("main") or soup.body or soup
        text = container.get_text(" ", strip=True)
        return re.sub(r"\s+", " ", text)[: self.max_content_length]

    @staticmethod
    def _result(source, status, title="", url="", published="", content="") -> dict:
        source = source or {}
        return {
            "title": title or "",
            "url": url or source.get("url") or "",
            "source_name": source.get("source_name") or "",
            "published": published or "",
            "content": content or "",
            "fetch_status": status,
        }


def run_selftest() -> int:
    from types import SimpleNamespace

    global feedparser, requests

    fake_feed = SimpleNamespace(
        entries=[
            SimpleNamespace(
                title="RSS测试标题",
                link="https://example.com/post/1",
                published="2026-08-09 10:00",
                summary="RSS测试摘要",
            )
        ],
        bozo=0,
    )

    class _FakeFeedParser:
        @staticmethod
        def parse(url):
            return fake_feed

    class _FakeResponse:
        status_code = 200
        text = (
            "<html><head><title>HTML测试标题</title></head>"
            "<body><article><p>正文内容一</p><p>正文内容二</p></article></body></html>"
        )

    class _FakeRequests:
        @staticmethod
        def get(url, timeout=10):
            return _FakeResponse()

    class _FailingRequests:
        @staticmethod
        def get(url, timeout=10):
            raise ConnectionError("mock network error")

    old_feedparser, old_requests = feedparser, requests
    all_ok = True

    try:
        fetcher = GameSourceFetcher()

        feedparser = _FakeFeedParser()
        requests = _FakeRequests()

        rss_result = fetcher.fetch_source(
            {
                "source_name": "测试RSS",
                "source_type": "RSS",
                "url": "https://example.com/feed",
                "priority": 100,
                "fetch_method": "RSS",
            }
        )
        ok = (
            rss_result["fetch_status"] == "success"
            and rss_result["title"] == "RSS测试标题"
            and rss_result["url"] == "https://example.com/post/1"
            and rss_result["published"] == "2026-08-09 10:00"
            and rss_result["content"] == "RSS测试摘要"
            and rss_result["source_name"] == "测试RSS"
        )
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] RSS mock: {json.dumps(rss_result, ensure_ascii=False)}")

        html_result = fetcher.fetch_source(
            {
                "source_name": "测试HTML",
                "source_type": "官网",
                "url": "https://example.com/news",
                "priority": 100,
                "fetch_method": "HTML",
            }
        )
        ok = (
            html_result["fetch_status"] == "success"
            and html_result["title"] == "HTML测试标题"
            and "正文内容一" in html_result["content"]
            and "正文内容二" in html_result["content"]
            and html_result["url"] == "https://example.com/news"
        )
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] HTML mock: {json.dumps(html_result, ensure_ascii=False)}")

        api_result = fetcher.fetch_source(
            {
                "source_name": "测试API",
                "source_type": "API",
                "url": "https://example.com/api",
                "priority": 100,
                "fetch_method": "API",
            }
        )
        ok = api_result["fetch_status"] == "unsupported"
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] API 未配置: {json.dumps(api_result, ensure_ascii=False)}")

        requests = _FailingRequests()
        isolated = fetcher.fetch_sources(
            [
                {
                    "source_name": "测试RSS",
                    "source_type": "RSS",
                    "url": "https://example.com/feed",
                    "priority": 100,
                    "fetch_method": "RSS",
                },
                {
                    "source_name": "失败HTML",
                    "source_type": "官网",
                    "url": "https://example.com/broken",
                    "priority": 100,
                    "fetch_method": "HTML",
                },
                {
                    "source_name": "测试API",
                    "source_type": "API",
                    "url": "https://example.com/api",
                    "priority": 100,
                    "fetch_method": "API",
                },
            ]
        )
        statuses = [item["fetch_status"] for item in isolated]
        ok = statuses == ["success", "fail", "unsupported"]
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] 单来源失败隔离: {statuses}")
    finally:
        feedparser, requests = old_feedparser, old_requests

    return 0 if all_ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="官方信息源抓取适配层")
    parser.add_argument("--game-id", help="游戏 ID")
    parser.add_argument("--event-type", help="事件类型")
    parser.add_argument("--source", help="单个来源配置 JSON 字符串")
    parser.add_argument("--registry", help="自定义注册表 JSON 路径")
    parser.add_argument("--selftest", action="store_true", help="运行内置 mock 验证")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    fetcher = GameSourceFetcher(registry_path=args.registry)
    if args.source:
        source = json.loads(args.source)
        results = fetcher.fetch_sources([source])
    elif args.game_id:
        results = fetcher.fetch_game_sources(args.game_id, args.event_type)
    else:
        parser.error("需要 --selftest、--source 或 --game-id")

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
