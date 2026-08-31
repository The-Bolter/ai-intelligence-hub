import json
from pathlib import Path

import game_source_fetcher as fetcher_module
from event_classifier import EventClassifier
from game_resolver import GameResolver
from game_source_fetcher import GameSourceFetcher
from gaming_collector import GamingCollector
from gaming_event_normalizer import extract_event_dates
from source_selector import SourceSelector


class _Response:
    status_code = 200

    def __init__(self, content, encoding=None, apparent_encoding=None):
        self.content = content if isinstance(content, bytes) else content.encode("utf-8")
        self.encoding = encoding
        self.apparent_encoding = apparent_encoding
        self.text = self.content.decode(encoding or "utf-8", errors="replace")


class _Requests:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, timeout=10):
        self.calls.append(url)
        return self.responses[url]


def _html_source(url="https://game.example/news"):
    return {
        "game_id": "GAME-1",
        "source_name": "游戏官网",
        "source_type": "官网",
        "url": url,
        "priority": 100,
        "fetch_method": "HTML",
    }


def _fetch(monkeypatch, responses, source=None):
    monkeypatch.setattr(fetcher_module, "requests", _Requests(responses))
    return GameSourceFetcher().fetch_source(source or _html_source())


def test_loading_and_weibo_access_wall_are_invalid(monkeypatch):
    for title, body in (("米游社", "Loading..."), ("Sina Visitor System", "")):
        url = "https://game.example/news"
        result = _fetch(monkeypatch, {url: _Response(f"<title>{title}</title><body>{body}</body>")})
        assert result["fetch_status"] == "invalid_page"
        assert result["invalid_reason"] == "placeholder_or_access_wall"


def test_empty_body_is_invalid(monkeypatch):
    url = "https://game.example/news"
    result = _fetch(monkeypatch, {url: _Response("<title>版本更新公告</title><body></body>")})
    assert result["fetch_status"] == "invalid_page"
    assert result["invalid_reason"] == "empty_body"


def test_gbk_page_decodes_correctly(monkeypatch):
    url = "https://game.example/news/patch"
    html = "<title>游戏版本更新公告</title><article>游戏将于2026年9月1日更新，新英雄上线并开启周年活动。</article>"
    result = _fetch(
        monkeypatch,
        {url: _Response(html.encode("gbk"), encoding="ISO-8859-1", apparent_encoding="GBK")},
        _html_source(url),
    )
    assert result["fetch_status"] == "success"
    assert "游戏版本更新公告" in result["title"]
    assert "新英雄" in result["content"]


def test_news_list_fetches_specific_announcement_link(monkeypatch):
    list_url = "https://game.example/news"
    article_url = "https://game.example/news/patch-2"
    listing = "<title>游戏官网</title><body><a href='/news/patch-2'>版本更新公告</a><footer>footer</footer></body>"
    article = "<title>2.0版本更新公告</title><article>2.0版本将于2026年9月2日更新，带来新英雄、新地图和周年活动。</article>"
    result = _fetch(monkeypatch, {list_url: _Response(listing), article_url: _Response(article)})
    assert result["fetch_status"] == "success"
    assert result["url"] == article_url
    assert result["source_is_article"] is True
    assert "2.0版本" in result["title"]


def test_explicit_article_source_is_not_reexpanded_as_a_listing(monkeypatch):
    article_url = "https://game.example/news/patch-2"
    detail = (
        "<title>2.0版本更新公告</title>"
        "<article>2.0版本将于2026年9月2日更新，带来新英雄和新地图。</article>"
        "<a href='/news/old'>旧新闻</a>"
    )
    result = _fetch(
        monkeypatch,
        {article_url: _Response(detail)},
        {**_html_source(article_url), "is_article": True},
    )
    assert result["fetch_status"] == "success"
    assert result["url"] == article_url
    assert "2.0版本" in result["title"]


def test_portfolio_article_metadata_is_preserved(monkeypatch):
    article_url = "https://game.example/news/event"
    detail = "<title>活动公告</title><article>活动详情。</article>"
    result = _fetch(
        monkeypatch,
        {article_url: _Response(detail)},
        {
            **_html_source(article_url), "is_article": True,
            "event_type": "major_event", "event_name": "Space Program",
            "start_date": "2026-09-03", "end_date": "2026-09-21",
            "key_changes": ["新活动"],
        },
    )
    assert result["event_type"] == "major_event"
    assert result["event_name"] == "Space Program"
    assert result["start_date"] == "2026-09-03"
    assert result["end_date"] == "2026-09-21"
    assert result["key_changes"] == ["新活动"]


class _Pipeline:
    class resolver:
        games = [{
            "game_id": "GAME-1", "name_cn": "示例游戏", "name_en": "Example Game",
            "platforms": ["pc"], "display_group": "pc",
        }]


def test_publisher_page_cannot_force_source_game_context():
    collector = GamingCollector(selector=object(), fetcher=object(), pipeline=_Pipeline(), event_store_path=None)
    generic = collector._safe_source_context(
        {"source_is_article": True, "source_url": "https://www.warnerbros.com/news"}, "GAME-1"
    )
    specific = collector._safe_source_context(
        {"source_is_article": True, "source_url": "https://game.example/news/1"}, "GAME-1"
    )
    assert generic is None
    assert specific["game_id"] == "GAME-1"
    assert specific["game_name"] == "示例游戏"


def test_dd_mm_yyyy_and_homepage_history_date_binding():
    start, end = extract_event_dates({"title": "新英雄将于11.09.2026上线"})
    assert start.isoformat() == "2026-09-11"
    assert end is None

    start, end = extract_event_dates({
        "title": "Game Home",
        "content": "Latest News 2026-08-26 Patch history and navigation",
        "source_is_article": False,
    })
    assert start is None and end is None


class _NoResolver:
    def resolve(self, *args, **kwargs):
        return {"matched": False}


def test_explicit_classifier_fallbacks(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"games": [], "event_rules": []}), encoding="utf-8")
    classifier = EventClassifier(path, resolver=_NoResolver())
    assert classifier.classify("New Hero Ye Xiu is available", game_id="GAME")["event_type"] == "new_character"
    assert classifier.classify("周年庆活动现已开启", game_id="GAME")["event_type"] == "major_event"
    assert classifier.classify("World Championship tournament begins", game_id="GAME")["event_type"] == "esports"


def test_call_of_duty_registry_entry_and_official_source():
    registry = json.loads(Path("config/game_registry.json").read_text(encoding="utf-8"))
    assert any(game.get("game_id") == "GACT-COD" for game in registry["games"])
    resolved = GameResolver().resolve("Call of Duty update")
    assert resolved["game_id"] == "GACT-COD"
    sources = SourceSelector().select("GACT-COD", "major_update")["sources"]
    assert sources and sources[0]["url"] == (
        "https://support.activision.com/no/modern-warfare-4/articles/modern-warfare-4-open-beta"
    )
