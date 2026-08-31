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
from urllib.parse import urljoin, urlsplit

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
            is_article=True,
        )

    def _fetch_html(self, source) -> dict:
        if requests is None or BeautifulSoup is None:
            return self._result(source, "fail")
        response = requests.get(source.get("url") or "", timeout=self.timeout)
        if getattr(response, "status_code", None) != 200:
            return self._result(source, "fail")
        soup = BeautifulSoup(self._response_text(response), "html.parser")
        if source.get("is_article"):
            title = soup.title.get_text(strip=True) if soup.title else ""
            content = self._body_text(soup)
            reason = self._invalid_reason(title, content, source.get("url") or "", is_article=True)
            if reason:
                return self._result(source, "invalid_page", invalid_reason=reason)
            return self._result(
                source, "success", title=title, content=content,
                url=source.get("url") or "", is_article=True,
            )
        article_url = self._find_article_link(soup, source.get("url") or "")
        if article_url:
            article_response = requests.get(article_url, timeout=self.timeout)
            if getattr(article_response, "status_code", None) != 200:
                return self._result(source, "fail")
            soup = BeautifulSoup(self._response_text(article_response), "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else ""
            content = self._body_text(soup)
            reason = self._invalid_reason(title, content, article_url, is_article=True)
            if reason:
                return self._result(source, "invalid_page", url=article_url, invalid_reason=reason)
            return self._result(
                source, "success", title=title, content=content, url=article_url,
                is_article=True,
            )
        title = soup.title.get_text(strip=True) if soup.title else ""
        content = self._body_text(soup)
        reason = self._invalid_reason(title, content, source.get("url") or "", is_article=False)
        if reason:
            return self._result(source, "invalid_page", invalid_reason=reason)
        return self._result(source, "success", title=title, content=content, is_article=False)

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
            content = self._response_text(response)
        reason = self._invalid_reason("", content, endpoint, is_article=True)
        if reason:
            return self._result(source, "invalid_page", invalid_reason=reason)
        return self._result(source, "success", content=content[: self.max_content_length], is_article=True)

    @staticmethod
    def _response_text(response) -> str:
        """Decode HTML deterministically, including common Chinese encodings."""
        raw = getattr(response, "content", None)
        if not isinstance(raw, (bytes, bytearray)):
            return str(getattr(response, "text", "") or "")
        encodings = []
        for encoding in (
            getattr(response, "encoding", None),
            getattr(response, "apparent_encoding", None),
            "utf-8", "gb18030", "gbk", "gb2312",
        ):
            normalized = str(encoding or "").strip()
            if normalized and normalized.casefold() not in {item.casefold() for item in encodings}:
                encodings.append(normalized)
        decoded = []
        for encoding in encodings:
            try:
                text = bytes(raw).decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
            # Prefer readable CJK/ASCII text and reject mojibake replacement noise.
            quality = sum(char.isascii() or "\u4e00" <= char <= "\u9fff" for char in text) - text.count("\ufffd") * 20
            decoded.append((quality, text))
        if decoded:
            return max(decoded, key=lambda value: value[0])[1]
        return bytes(raw).decode("utf-8", errors="replace")

    def _find_article_link(self, soup, base_url: str) -> str | None:
        """Choose one same-site, event-oriented article link from a list page."""
        parsed_base = urlsplit(base_url)
        positives = ("公告", "新闻", "版本", "更新", "活动", "赛事", "notice", "news", "update", "patch", "event")
        negatives = ("首页", "home", "footer", "forum", "论坛", "status", "login", "登录", "用户中心")
        candidates = []
        for link in soup.find_all("a", href=True):
            href = str(link.get("href") or "").strip()
            text = link.get_text(" ", strip=True)
            absolute = urljoin(base_url, href)
            parsed = urlsplit(absolute)
            if not href or href.startswith("#") or parsed.scheme not in ("http", "https"):
                continue
            if parsed.hostname != parsed_base.hostname or absolute.rstrip("/") == base_url.rstrip("/"):
                continue
            material = f"{text} {parsed.path}".casefold()
            if any(token in material for token in negatives):
                continue
            score = sum(token in material for token in positives)
            if score:
                candidates.append((score, len(text), absolute))
        return max(candidates, default=(0, 0, None))[2]

    @staticmethod
    def _invalid_reason(title: str, content: str, url: str, is_article: bool) -> str | None:
        title = str(title or "").strip()
        content = re.sub(r"\s+", " ", str(content or "")).strip()
        material = f"{title} {content}".casefold()
        if any(marker in material for marker in (
            "loading...", "sina visitor system", "javascript required", "enable javascript",
            "access denied", "login required", "请先登录",
        )):
            return "placeholder_or_access_wall"
        if not content:
            return "empty_body"
        path = urlsplit(url).path.casefold()
        if any(marker in path for marker in ("/forum", "/forums", "/community", "/status", "/login")):
            return "forum_status_or_login_page"
        if not is_article and (path in ("", "/") or any(marker in title.casefold() for marker in ("official website", "官方网站", "官网首页"))):
            return "homepage_or_navigation"
        event_terms = ("公告", "新闻", "版本", "更新", "活动", "赛事", "notice", "news", "update", "patch", "event", "beta", "launch")
        if len(content) < 80 and not any(term in material for term in event_terms):
            return "too_short_without_event_signal"
        return None

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
    def _result(
        source, status, title="", url="", published="", content="", invalid_reason=None,
        is_article=False,
    ) -> dict:
        source = source or {}
        return {
            "title": title or "",
            "url": url or source.get("url") or "",
            "source_name": source.get("source_name") or "",
            "source_type": source.get("source_type") or "",
            "source_priority": source.get("priority", source.get("source_priority")),
            "source_url": source.get("url") or source.get("URL") or "",
            "published": published or "",
            "content": content or "",
            "fetch_status": status,
            "invalid_reason": invalid_reason,
            "source_is_article": bool(is_article),
            # Portfolio records may carry verified metadata from the same
            # concrete official article.  The Collector forwards it unchanged
            # to the existing deterministic normalizer.
            "event_type": source.get("event_type"),
            "event_name": source.get("event_name"),
            "start_date": source.get("start_date"),
            "end_date": source.get("end_date"),
            "key_changes": list(source.get("key_changes") or []),
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
            "<body><article><p>正文内容一：2.0版本更新公告。</p>"
            "<p>正文内容二：新英雄将于2026年9月1日上线，活动同步开启。</p></article></body></html>"
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
