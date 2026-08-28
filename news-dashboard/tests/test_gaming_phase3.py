from datetime import datetime
from zoneinfo import ZoneInfo

import app as app_module
from gaming_event_store import GamingEventStore


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _confirmed(today):
    return {
        "event_id": "event-phase3",
        "game_id": "GAME-1",
        "game_name": "示例游戏",
        "platforms": ["mobile", "pc"],
        "display_group": "mobile",
        "event_type": "major_update",
        "event_name": "4.5版本更新",
        "start_date": today,
        "end_date": None,
        "key_changes": ["新角色", "新活动"],
        "recommended_sources": [
            {"url": "https://official.example/news", "official": True, "priority": 100}
        ],
        "source_article_ids": ["article-1"],
    }


def test_store_save_load_preserves_first_detected(tmp_path):
    path = tmp_path / "store.json"
    store = GamingEventStore()
    event = _confirmed("2026-08-28")
    store.ingest({"events": [event], "pending": []}, "2026-08-28T08:00:00+08:00")
    first = store.confirmed_events()[0]["first_detected_at"]
    store.save(path)
    loaded = GamingEventStore.load(path)
    loaded.ingest({"events": [event], "pending": []}, "2026-08-28T12:00:00+08:00")
    assert loaded.confirmed_events()[0]["first_detected_at"] == first


def test_weekly_and_today_new_api_schema(tmp_path, monkeypatch):
    now = datetime.now(SHANGHAI)
    path = tmp_path / "store.json"
    store = GamingEventStore()
    store.ingest({"events": [_confirmed(now.date().isoformat())], "pending": []}, now)
    store.save(path)
    monkeypatch.setattr(app_module, "GAMING_EVENT_STORE_FILE", path)

    client = app_module.app.test_client()
    weekly_response = client.get("/api/gaming/weekly")
    weekly = weekly_response.get_json()
    assert weekly_response.status_code == 200
    assert weekly["schema_version"] == 3
    assert weekly["view"] == "weekly_radar"
    event = weekly["events"][0]
    required = {
        "event_id", "game_id", "game_name", "platforms", "display_group",
        "event_type", "event_name", "start_date", "end_date", "phase",
        "attention_level", "hotspot_score", "score_factors", "key_changes",
        "summary", "impact_types", "recommended_sources",
        "first_detected_at", "last_detected_at",
    }
    assert required <= event.keys()

    today_response = client.get("/api/gaming/today-new")
    today = today_response.get_json()
    assert today_response.status_code == 200
    assert today["view"] == "today_new"
    assert today["items"][0]["event_id"] == "event-phase3"
    assert today["items"][0]["detected_at"]


def test_legacy_hotspots_api_is_unchanged(tmp_path, monkeypatch):
    old_path = tmp_path / "gaming_hotspots.json"
    old_path.write_text(
        '{"hotspots":[{"game_name":"旧链路游戏","event_type":"version_update",'
        '"importance":"高","hotspot_score":70,"recommended_sources":[]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "GAMING_HOTSPOTS_FILE", str(old_path))
    response = app_module.app.test_client().get("/api/gaming/hotspots")
    assert response.status_code == 200
    assert response.get_json()["items"][0]["game_name"] == "旧链路游戏"
