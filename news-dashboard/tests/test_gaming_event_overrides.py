from __future__ import annotations

import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gaming_event_store import GamingEventStore  # noqa: E402
from gaming_weekly_v2 import build_weekly_radar  # noqa: E402


WXQ_ID = "5320a65135c7002a76a03997"
MW4_ID = "0511e4a9ec24d77c07aca81e"


def upstream_event(event_id, **overrides):
    event = {
        "event_id": event_id,
        "game_id": "GAME",
        "game_name": "测试游戏",
        "event_name": "上游事件",
        "event_type": "test_or_launch",
        "platforms": ["mobile", "pc"],
        "display_group": "mobile",
        "start_date": "2026-09-02",
        "end_date": None,
        "key_changes": ["上游字段"],
        "recommended_sources": [],
        "source_article_ids": [],
    }
    event.update(overrides)
    return event


def test_manual_overrides_survive_repeated_upstream_ingest():
    store = GamingEventStore()
    for detected_at in ("2026-09-06T10:00:00+08:00", "2026-09-07T10:00:00+08:00"):
        store.ingest(
            {"events": [upstream_event(WXQ_ID), upstream_event(MW4_ID)], "pending": []},
            detected_at=detected_at,
        )

    wxq = store.confirmed_event(WXQ_ID)
    mw4 = store.confirmed_event(MW4_ID)
    assert wxq["event_type"] == "test_or_launch"  # Canonical classification remains unchanged.
    assert wxq["event_stage"] == "pre_registration"
    assert wxq["event_stage_label"] == "预注册"
    assert wxq["end_date"] == "2026-09-10"
    assert "9月9日开启正式包预下载" in wxq["summary"]
    assert mw4["platforms"] == ["pc"]
    assert mw4["display_group"] == "pc"

    weekly = build_weekly_radar(store, "2026-09-07T12:00:00+08:00")
    wxq_weekly = next(event for event in weekly["events"] if event["event_id"] == WXQ_ID)
    assert wxq_weekly["phase"] == "active"
    assert wxq_weekly["event_stage_label"] == "预注册"


def test_manual_overrides_apply_when_an_existing_store_is_loaded():
    store = GamingEventStore({"events": [upstream_event(WXQ_ID)], "pending_events": []})
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "event_store.json"
        store.save(path)
        loaded = GamingEventStore.load(path)
    event = loaded.confirmed_event(WXQ_ID)
    assert event["event_stage_label"] == "预注册"
    assert event["end_date"] == "2026-09-10"
