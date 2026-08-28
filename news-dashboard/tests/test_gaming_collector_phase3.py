from gaming_collector import GamingCollector
from gaming_event_store import GamingEventStore


class FakeSelector:
    def select(self, game_id, event_type):
        return {"sources": [{"url": "https://official.example/feed", "priority": 100}]}


class FakeFetcher:
    def fetch_sources(self, sources):
        return [{
            "title": "示例游戏4.5版本于8月28日更新，新角色上线",
            "content": "完整正文",
            "url": "https://official.example/article/1",
            "source_name": "示例游戏官网",
            "source_type": "官方公告",
            "priority": 100,
            "published": "2026-08-20T09:00:00+08:00",
            "custom_metadata": {"channel": "news"},
            "fetch_status": "success",
        }]


class FakePipeline:
    def __init__(self):
        self.articles = None

    def process_articles(self, articles):
        return [{"game_name": "旧链路结果", "hotspot_score": 70}]

    def normalize_articles(self, articles):
        self.articles = articles
        return {"events": [{
            "event_id": "event-1", "game_id": "GAME-1", "game_name": "示例游戏",
            "platforms": ["mobile"], "display_group": "mobile",
            "event_type": "major_update", "event_name": "4.5版本更新",
            "start_date": "2026-08-28", "end_date": None,
            "key_changes": ["新角色"], "recommended_sources": [],
            "source_article_ids": ["https://official.example/article/1"],
            "source_articles": articles,
        }], "pending": []}


def test_collector_keeps_metadata_and_writes_parallel_store(tmp_path):
    pipeline = FakePipeline()
    path = tmp_path / "store.json"
    collector = GamingCollector(
        selector=FakeSelector(), fetcher=FakeFetcher(), pipeline=pipeline,
        event_store=GamingEventStore(), event_store_path=path,
    )
    result = collector.collect_game_events("GAME-1", "major_update")
    assert result["hotspots"][0]["game_name"] == "旧链路结果"
    assert pipeline.articles[0]["custom_metadata"] == {"channel": "news"}
    assert pipeline.articles[0]["content"] == "完整正文"
    assert path.is_file()
    stored = GamingEventStore.load(path).confirmed_events()[0]
    assert stored["source_articles"][0]["custom_metadata"] == {"channel": "news"}
