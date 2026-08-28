from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from event_classifier import EventClassifier  # noqa: E402
from game_resolver import GameResolver  # noqa: E402
from gaming_event_normalizer import normalize_event  # noqa: E402
from gaming_pipeline import GamingPipeline  # noqa: E402
from gaming_v2_rules import CANONICAL_EVENT_TYPES  # noqa: E402


REFERENCE = date(2026, 8, 28)
GAME = {
    "matched": True,
    "game_id": "GAME-TEST",
    "game_name": "测试游戏",
    "platforms": ["mobile", "pc"],
    "display_group": "mobile",
}
CLASSIFICATION = {
    "matched": True,
    "event_type": "major_update",
    "event_name": "2.0 版本更新",
}


def normalized(text, **overrides):
    article = {
        "title": text,
        "summary": text,
        "version": "2.0",
    }
    article.update(overrides)
    return normalize_event(article, GAME, CLASSIFICATION, reference_date=REFERENCE)


class _FakeResolver:
    def resolve(self, title, summary=None):
        return dict(GAME)


class _FakeClassifier:
    def classify(self, title, summary=None, game_id=None):
        return {
            "matched": True,
            "event_type": "major_update",
            "event_name": "2.0 版本更新",
            "importance": "高",
            "legacy_event_type": "version_update",
        }


class _FakeSelector:
    def select(self, game_id, event_type):
        return {
            "game_id": game_id,
            "event_type": event_type,
            "sources": [
                {
                    "source_name": "游戏官网",
                    "source_type": "官网",
                    "url": "https://example.com/news",
                    "priority": 100,
                    "fetch_method": "HTML",
                }
            ],
        }


def _pipeline():
    return GamingPipeline(
        resolver=_FakeResolver(),
        classifier=_FakeClassifier(),
        selector=_FakeSelector(),
    )


def test_chinese_single_date():
    event = normalized("2.0版本将于2026年8月29日上线")
    assert event["start_date"] == "2026-08-29"
    assert event["end_date"] is None


def test_english_single_date():
    event = normalized("Version 2.0 launches August 29, 2026")
    assert event["start_date"] == "2026-08-29"


def test_iso_date():
    event = normalized("Version 2.0 launches 2026-08-29")
    assert event["start_date"] == "2026-08-29"


def test_chinese_date_range_and_cross_month():
    event = normalized("测试时间为2026年8月29日至9月2日")
    assert event["start_date"] == "2026-08-29"
    assert event["end_date"] == "2026-09-02"


def test_english_date_range():
    event = normalized("Beta runs August 29 to September 2, 2026")
    assert event["start_date"] == "2026-08-29"
    assert event["end_date"] == "2026-09-02"


def test_cross_year_range():
    event = normalized("活动时间为2026年12月30日至2027年1月2日")
    assert event["start_date"] == "2026-12-30"
    assert event["end_date"] == "2027-01-02"


def test_future_event_date_is_kept():
    event = normalized("测试将于2026年9月5日开始")
    assert event["start_date"] == "2026-09-05"
    assert event["event_id"] is not None


def test_published_at_is_never_an_event_date():
    event = normalized(
        "2.0版本内容已公布",
        published_at="2026-08-29T10:00:00+08:00",
        published="2026-08-29T10:00:00+08:00",
    )
    assert event["start_date"] is None
    assert event["end_date"] is None
    assert event["event_id"] is None


def test_missing_date_enters_pending():
    result = _pipeline().normalize_article(
        {"title": "2.0版本内容已公布", "summary": "包含新地图和新角色"},
        reference_date=REFERENCE,
    )
    assert result["events"] == []
    assert len(result["pending"]) == 1
    assert result["pending"][0]["event_id"] is None


def test_event_id_is_stable():
    first = normalized("2.0版本将于2026年8月29日上线")
    second = normalized("2.0版本将于2026年8月29日上线")
    assert first["event_id"] == second["event_id"]
    assert len(first["event_id"]) == 24


def test_multi_platform_and_display_group_from_registry():
    registry = {
        "games": [
            {
                "game_id": "GAME-CROSS",
                "游戏名称": "跨平台游戏",
                "英文名称": "Cross Platform Game",
                "平台": "PC/Mobile",
            }
        ]
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "registry.json"
        path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
        result = GameResolver(path).resolve("跨平台游戏版本更新")
    assert result["platforms"] == ["mobile", "pc"]
    assert result["display_group"] == "mobile"


def test_explicit_platform_values_take_priority():
    registry = {
        "games": [
            {
                "game_id": "GAME-EXPLICIT",
                "游戏名称": "显式平台游戏",
                "平台": "Mobile",
                "platforms": ["pc"],
                "display_group": "pc",
            }
        ]
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "registry.json"
        path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
        result = GameResolver(path).resolve("显式平台游戏版本更新")
    assert result["platforms"] == ["pc"]
    assert result["display_group"] == "pc"


def test_key_changes_are_deterministic_and_explicit():
    event = normalized("2.0版本带来新地图、新角色、新玩法、新活动，并开启联动和公测")
    assert event["key_changes"] == ["新地图", "新角色", "新玩法", "新活动", "公测", "联动"]


def test_source_url_dedup_keeps_highest_priority():
    sources = [
        {
            "source_name": "低优先级",
            "source_type": "官网",
            "url": "https://example.com/news/",
            "priority": 50,
        },
        {
            "source_name": "游戏官网",
            "source_type": "官网",
            "url": "https://example.com/news",
            "priority": 100,
        },
    ]
    event = normalize_event(
        {"title": "2.0版本将于2026年8月29日上线", "version": "2.0"},
        GAME,
        CLASSIFICATION,
        recommended_sources=sources,
        reference_date=REFERENCE,
    )
    assert len(event["recommended_sources"]) == 1
    assert event["recommended_sources"][0]["priority"] == 100
    assert event["recommended_sources"][0]["name"] == "游戏官网"


def test_event_classifier_outputs_only_canonical_type():
    registry = {
        "games": [],
        "event_rules": [
            {
                "event_type": "version_update",
                "事件中文": "版本更新",
                "关键词(正则)": "major update",
                "匹配逻辑": "OR",
                "重要程度": "高",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "registry.json"
        path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
        result = EventClassifier(path, resolver=_FakeResolver()).classify(
            "Major Update launches soon", game_id="GAME-TEST"
        )
    assert result["event_type"] == "major_update"
    assert result["event_type"] in CANONICAL_EVENT_TYPES
    assert result["legacy_event_type"] == "version_update"


def test_legacy_pipeline_output_is_unchanged():
    result = _pipeline().process_article("测试游戏2.0版本更新", "版本内容")
    assert result["event_type"] == "version_update"
