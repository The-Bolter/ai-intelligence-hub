import json

import fetcher


def test_partial_persistence_preserves_failed_source(tmp_path, monkeypatch):
    path = tmp_path / "news_ai.json"
    old = {"category": "ai", "items": [{"id": "old", "source_name": "Broken", "title": "cached"}]}
    path.write_text(json.dumps(old), encoding="utf-8")
    monkeypatch.setattr(fetcher.config, "AI_DATA_FILE", str(path))
    fetcher._AI_SOURCE_FAILURES.clear()
    fetcher._AI_SOURCE_FAILURES["Broken"] = "TimeoutError: test"
    fetcher.save_news("ai", [{"id": "new", "source_name": "Healthy", "title": "fresh"}])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert {item["id"] for item in data["items"]} == {"old", "new"}
    fetcher._AI_SOURCE_FAILURES.clear()
