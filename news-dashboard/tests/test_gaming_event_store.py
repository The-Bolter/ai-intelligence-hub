from __future__ import annotations

import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gaming_event_store import GamingEventStore  # noqa: E402


def event(**overrides):
    value = {
        "event_id": "event-1",
        "game_id": "GAME-1",
        "game_name": "测试游戏",
        "platforms": ["mobile"],
        "display_group": "mobile",
        "event_type": "major_update",
        "event_name": "2.0版本更新",
        "start_date": "2026-08-29",
        "end_date": None,
        "key_changes": ["新地图"],
        "recommended_sources": [
            {
                "name": "游戏官网",
                "url": "https://example.com/a",
                "source_type": "official_site",
                "official": True,
                "priority": 100,
                "fetch_method": "HTML",
            }
        ],
        "source_article_ids": ["article-1"],
    }
    value.update(overrides)
    return value


def test_duplicate_event_merges_without_creating_a_second_event():
    store = GamingEventStore()
    first_stats = store.ingest(
        {"events": [event()], "pending": []},
        detected_at="2026-08-28T08:00:00+08:00",
    )
    second_stats = store.ingest(
        {
            "events": [
                event(
                    key_changes=["新角色"],
                    recommended_sources=[
                        {
                            "name": "官方社区",
                            "url": "https://example.com/b",
                            "source_type": "official_social",
                            "official": True,
                            "priority": 90,
                            "fetch_method": "API",
                        }
                    ],
                    source_article_ids=["article-2"],
                )
            ],
            "pending": [],
        },
        detected_at="2026-08-28T12:00:00+08:00",
    )

    events = store.confirmed_events()
    assert first_stats["confirmed_created"] == 1
    assert second_stats["confirmed_updated"] == 1
    assert len(events) == 1
    assert events[0]["first_detected_at"] == "2026-08-28T08:00:00+08:00"
    assert events[0]["last_detected_at"] == "2026-08-28T12:00:00+08:00"
    assert events[0]["key_changes"] == ["新地图", "新角色"]
    assert events[0]["source_article_ids"] == ["article-1", "article-2"]
    assert [source["url"] for source in events[0]["recommended_sources"]] == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_duplicate_source_url_keeps_highest_priority():
    store = GamingEventStore()
    store.ingest(
        {"events": [event()], "pending": []},
        detected_at="2026-08-28T08:00:00+08:00",
    )
    store.ingest(
        {
            "events": [
                event(
                    recommended_sources=[
                        {
                            "name": "更高优先级官网",
                            "url": "https://example.com/a/",
                            "source_type": "official_site",
                            "official": True,
                            "priority": 120,
                            "fetch_method": "API",
                        }
                    ]
                )
            ]
        },
        detected_at="2026-08-28T09:00:00+08:00",
    )
    sources = store.confirmed_events()[0]["recommended_sources"]
    assert len(sources) == 1
    assert sources[0]["priority"] == 120
    assert sources[0]["name"] == "更高优先级官网"


def test_pending_is_saved_separately_and_upgrades_when_date_is_confirmed():
    store = GamingEventStore()
    pending = event(event_id=None, start_date=None, end_date=None)
    store.ingest(
        {"events": [], "pending": [pending]},
        detected_at="2026-08-27T10:00:00+08:00",
    )
    assert store.confirmed_events() == []
    assert len(store.pending_events()) == 1
    assert store.pending_events()[0]["pending_key"].startswith("pending-")
    assert store.pending_events()[0]["event_id"] is None

    stats = store.ingest(
        {"events": [event()], "pending": []},
        detected_at="2026-08-28T10:00:00+08:00",
    )
    assert stats["pending_upgraded"] == 1
    assert store.pending_events() == []
    assert len(store.confirmed_events()) == 1
    assert store.confirmed_events()[0]["first_detected_at"] == "2026-08-27T10:00:00+08:00"
    assert store.confirmed_events()[0]["last_detected_at"] == "2026-08-28T10:00:00+08:00"


def test_store_round_trip_is_stable_when_explicitly_saved():
    store = GamingEventStore()
    store.ingest(
        {"events": [event()], "pending": []},
        detected_at="2026-08-28T08:00:00+08:00",
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "event_store.json"
        expected = store.save(path)
        loaded = GamingEventStore.load(path)
    assert loaded.to_dict() == expected


def test_remove_confirmed_removes_only_the_target_event():
    store = GamingEventStore()
    store.ingest({"events": [event(), event(event_id="event-2")], "pending": []})
    assert store.remove_confirmed("event-1") is True
    assert [item["event_id"] for item in store.confirmed_events()] == ["event-2"]
