from datetime import date

import app as app_module
from gaming_event_detail import build_event_detail
from gaming_event_store import GamingEventStore


def event(**overrides):
    base = {"event_id": "evt-1", "game_id": "game", "game_name": "游戏", "event_name": "版本更新", "event_type": "major_update", "start_date": "2026-09-04", "end_date": None, "hotspot_score": 80, "impact_types": ["retention"], "source_articles": [{"source_id": "media", "source_role": "secondary", "article_id": "a1", "url": "https://media/a", "title": "媒体", "published_at": "2026-09-03T09:00:00+08:00"}, {"source_id": "official", "source_role": "official", "article_id": "a2", "url": "https://official/a", "title": "官方", "published_at": "2026-09-02T09:00:00+08:00"}, {"source_id": "official", "source_role": "official", "article_id": "a2", "url": "https://official/a", "published_at": "2026-09-02T09:00:00+08:00"}], "date_evidence": [{"source_article_id": "a2", "source_url": "https://official/a", "start_date": "2026-09-04", "evidence_type": "explicit_date"}], "first_detected_at": "2026-09-03T10:00:00+08:00", "last_verified_at": "2026-09-03T11:00:00+08:00"}
    base.update(overrides); return base


def test_verified_detail_orders_sources_and_timeline():
    detail = build_event_detail(event(), date(2026, 9, 4))
    assert detail["verification_status"] == "verified"
    assert detail["sources"][0]["url"] == "https://official/a"
    assert len(detail["sources"]) == 2
    assert detail["status"] == "active"
    assert detail["timeline"] == sorted(detail["timeline"], key=lambda node: str(node["date"]))


def test_partial_without_complete_evidence():
    assert build_event_detail(event(date_evidence=[]))["verification_status"] == "partial"
    assert build_event_detail(event(source_articles=[]))["verification_status"] == "partial"


def test_route_returns_detail_and_404(monkeypatch):
    store = GamingEventStore({"events": [event()]})
    monkeypatch.setattr(app_module, "_load_gaming_event_store", lambda: store)
    client = app_module.app.test_client()
    assert client.get("/api/gaming/events/evt-1").status_code == 200
    response = client.get("/api/gaming/events/missing")
    assert response.status_code == 404 and response.get_json() == {"error": "event_not_found"}
