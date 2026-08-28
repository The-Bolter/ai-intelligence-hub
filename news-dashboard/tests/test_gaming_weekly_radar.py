from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gaming_event_store import GamingEventStore  # noqa: E402
from gaming_weekly_v2 import (  # noqa: E402
    build_today_new,
    build_weekly_radar,
    compute_event_phase,
)


REFERENCE = "2026-08-28T12:00:00+08:00"


def event(event_id, start_date, end_date=None, **overrides):
    value = {
        "event_id": event_id,
        "game_id": "GAME-1",
        "game_name": "测试游戏",
        "platforms": ["mobile"],
        "display_group": "mobile",
        "event_type": "major_update",
        "event_name": event_id,
        "start_date": start_date,
        "end_date": end_date,
        "key_changes": [],
        "recommended_sources": [],
        "source_article_ids": [],
    }
    value.update(overrides)
    return value


def store_with(events, detected_at="2026-08-28T09:00:00+08:00", pending=None):
    store = GamingEventStore()
    store.ingest(
        {"events": events, "pending": pending or []},
        detected_at=detected_at,
    )
    return store


def test_phase_upcoming_active_and_ended():
    assert compute_event_phase(event("future", "2026-08-29"), REFERENCE) == "upcoming"
    assert compute_event_phase(event("active-range", "2026-08-27", "2026-08-29"), REFERENCE) == "active"
    assert compute_event_phase(event("ended-range", "2026-08-20", "2026-08-27"), REFERENCE) == "ended"
    assert compute_event_phase(event("active-day", "2026-08-28"), REFERENCE) == "active"
    assert compute_event_phase(event("ended-day", "2026-08-27"), REFERENCE) == "ended"


def test_single_day_and_future_events_enter_current_week():
    store = store_with([
        event("today", "2026-08-28"),
        event("future", "2026-08-30"),
        event("outside", "2026-08-31"),
    ])
    radar = build_weekly_radar(store, REFERENCE)
    assert radar["week_start"] == "2026-08-24"
    assert radar["week_end"] == "2026-08-30"
    assert [item["event_id"] for item in radar["events"]] == ["today", "future"]
    assert radar["events"][1]["phase"] == "upcoming"


def test_cross_week_event_enters_when_interval_intersects():
    store = store_with([event("cross-week", "2026-08-20", "2026-08-25")])
    radar = build_weekly_radar(store, REFERENCE)
    assert [item["event_id"] for item in radar["events"]] == ["cross-week"]


def test_cross_month_interval_intersects_week():
    store = store_with([event("cross-month", "2026-08-30", "2026-09-02")])
    radar = build_weekly_radar(store, "2026-09-01T12:00:00+08:00")
    assert radar["week_start"] == "2026-08-31"
    assert radar["week_end"] == "2026-09-06"
    assert radar["events"][0]["event_id"] == "cross-month"


def test_cross_year_interval_intersects_week():
    store = store_with([event("cross-year", "2026-12-30", "2027-01-02")])
    radar = build_weekly_radar(store, "2027-01-01T12:00:00+08:00")
    assert radar["week_start"] == "2026-12-28"
    assert radar["week_end"] == "2027-01-03"
    assert radar["events"][0]["event_id"] == "cross-year"
    assert radar["events"][0]["phase"] == "active"


def test_pending_is_not_a_confirmed_weekly_event():
    pending = event(None, None, event_name="待确认活动")
    store = store_with([event("confirmed", "2026-08-28")], pending=[pending])
    radar = build_weekly_radar(store, REFERENCE)
    assert [item["event_id"] for item in radar["events"]] == ["confirmed"]
    assert len(radar["pending_events"]) == 1
    assert radar["pending_events"][0]["event_id"] is None


def test_mobile_and_pc_platform_indexes():
    store = store_with([
        event("mobile-only", "2026-08-28", platforms=["mobile"]),
        event("pc-only", "2026-08-28", platforms=["pc"], display_group="pc"),
        event("cross", "2026-08-29", platforms=["mobile", "pc"]),
    ])
    radar = build_weekly_radar(store, REFERENCE)
    assert radar["platform_indexes"]["mobile"] == ["mobile-only", "cross"]
    assert radar["platform_indexes"]["pc"] == ["pc-only", "cross"]


def test_today_new_is_derived_from_current_week_only():
    store = GamingEventStore()
    store.ingest(
        {"events": [event("old-detection", "2026-08-29")]},
        detected_at="2026-08-27T09:00:00+08:00",
    )
    store.ingest(
        {
            "events": [
                event("today-new", "2026-08-30"),
                event("today-outside-week", "2026-08-31"),
            ]
        },
        detected_at="2026-08-28T10:00:00+08:00",
    )
    view = build_today_new(store, REFERENCE)
    assert view["view"] == "today_new"
    assert view["date"] == "2026-08-28"
    assert [item["event_id"] for item in view["items"]] == ["today-new"]
    assert view["items"][0]["detected_at"] == "2026-08-28T10:00:00+08:00"
