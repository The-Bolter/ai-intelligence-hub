import json

from export_static_snapshots import export_snapshots


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def get_json(self):
        return self.payload

    def get_data(self, as_text=False):
        return json.dumps(self.payload)


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads

    def get(self, endpoint):
        return FakeResponse(self.payloads[endpoint])


def test_export_snapshots_uses_public_api_shapes_and_writes_static_entry(tmp_path):
    template = tmp_path / "template.html"
    template.write_text(
        "<link href=\"{{ url_for('static', filename='style.css') }}\">\n"
        "    <script src=\"{{ url_for('static', filename='script.js') }}?v=22\"></script>\n",
        encoding="utf-8",
    )
    client = FakeClient({
        "/api/ai/today": {"view": "ai_today"},
        "/api/gaming/weekly": {"events": [{"event_id": "event-1"}]},
        "/api/gaming/today-new": {"items": [{"event_id": "event-2"}]},
        "/api/gaming/events/event-1": {"title": "Event one"},
        "/api/gaming/events/event-2": {"title": "Event two"},
    })

    result = export_snapshots(client, tmp_path / "static", template)

    assert result == {"ai_today": 1, "gaming_weekly": 1, "gaming_today_new": 1, "gaming_events": 2}
    assert json.loads((tmp_path / "static" / "data" / "ai_today.json").read_text(encoding="utf-8")) == {"view": "ai_today"}
    assert json.loads((tmp_path / "static" / "data" / "gaming_events" / "event-2.json").read_text(encoding="utf-8")) == {"title": "Event two"}
    index = (tmp_path / "static" / "index.html").read_text(encoding="utf-8")
    assert "window.STATIC_MODE=true" in index
    assert "{{ url_for" not in index
