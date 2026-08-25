"""Gaming hotspot aggregator.

Reads the game registry, iterates every game, calls
gaming_collector.collect_game_events for each game, aggregates all hotspots,
and writes the result to gaming_hotspots.json.

The aggregator accepts an injected collector so tests can run without
accessing real websites.

Usage:
    python gaming_aggregator.py [--event-type version_update] [--output gaming_hotspots.json]
    python gaming_aggregator.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from gaming_collector import GamingCollector
from source_selector import SourceSelector

DEFAULT_REGISTRY = Path(__file__).resolve().parent / "config" / "game_registry.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "gaming_hotspots.json"

_IMPORTANCE_RANK = {"高": 3, "中": 2, "低": 1}


def _importance_rank(value) -> int:
    return _IMPORTANCE_RANK.get(value, 0)


class GamingAggregator:
    def __init__(self, registry_path=None, collector=None):
        self.registry_path = Path(registry_path) if registry_path else DEFAULT_REGISTRY
        self.games = self._load_games()
        self._event_importance = self._load_event_importance()
        self._selector = None
        self.collector = collector if collector is not None else GamingCollector(registry_path=self.registry_path)

    def _load_games(self) -> list[dict]:
        if not self.registry_path.is_file():
            raise FileNotFoundError(f"游戏注册表不存在: {self.registry_path}")
        with self.registry_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        games = []
        for record in data.get("games", []):
            game_id = record.get("game_id")
            if not game_id:
                continue
            games.append(
                {
                    "game_id": game_id,
                    "game_name": record.get("游戏名称") or record.get("name_cn") or "",
                }
            )
        return games

    def _load_event_importance(self) -> dict:
        with self.registry_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        importance = {}
        for record in data.get("event_rules", []):
            game_id = record.get("game_id")
            event_type = record.get("event_type")
            value = record.get("重要程度") or record.get("importance")
            if game_id and event_type and value:
                importance[(game_id, event_type)] = value
        return importance

    def _get_selector(self) -> SourceSelector:
        if self._selector is None:
            self._selector = SourceSelector(registry_path=self.registry_path)
        return self._selector

    def aggregate(self, event_type=None, output_path=None) -> dict:
        merged_hotspots = {}
        checked_games = 0
        failed_games = 0
        sources_checked = 0
        articles_found = 0

        for game in self.games:
            checked_games += 1
            try:
                result = self.collector.collect_game_events(game["game_id"], event_type)
            except Exception:
                failed_games += 1
                continue

            sources_checked += result.get("sources_checked", 0)
            articles_found += result.get("articles_found", 0)
            for hotspot in result.get("hotspots", []):
                event_type_value = hotspot.get("event_type")
                score = hotspot.get("hotspot_score") or 0
                if event_type_value is None and score <= 0:
                    continue
                key = (game["game_id"], event_type_value)
                entry = merged_hotspots.get(key)
                if entry is None:
                    entry = {
                        "game_id": game["game_id"],
                        "game_name": hotspot.get("game_name") or game["game_name"],
                        "event_type": event_type_value,
                        "hotspot_score": score,
                        "importance": hotspot.get("importance"),
                        "recommended_sources": list(hotspot.get("recommended_sources") or []),
                        "articles_count": 1,
                    }
                    merged_hotspots[key] = entry
                else:
                    entry["articles_count"] += 1
                    new_importance = hotspot.get("importance")
                    if _importance_rank(new_importance) > _importance_rank(entry["importance"]):
                        entry["importance"] = new_importance
                    new_sources = list(hotspot.get("recommended_sources") or [])
                    if score > entry["hotspot_score"]:
                        entry["hotspot_score"] = score
                        entry["game_name"] = hotspot.get("game_name") or entry["game_name"]
                        if new_sources:
                            entry["recommended_sources"] = new_sources
                    elif not entry["recommended_sources"] and new_sources:
                        entry["recommended_sources"] = new_sources

        hotspots = list(merged_hotspots.values())
        for hotspot in hotspots:
            key = (hotspot["game_id"], hotspot["event_type"])
            if not hotspot["importance"]:
                hotspot["importance"] = self._event_importance.get(key)
            if not hotspot["recommended_sources"]:
                hotspot["recommended_sources"] = self._get_selector().select(
                    hotspot["game_id"], hotspot["event_type"] or ""
                ).get("sources", [])

        hotspots.sort(
            key=lambda item: (
                -item["hotspot_score"],
                item["game_name"] or "",
                item["game_id"] or "",
            )
        )

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_games": len(self.games),
            "checked_games": checked_games,
            "failed_games": failed_games,
            "sources_checked": sources_checked,
            "articles_found": articles_found,
            "hotspot_count": len(hotspots),
            "hotspots": hotspots,
        }

        if output_path is not None:
            target = Path(output_path)
            if not target.is_absolute():
                target = Path(__file__).resolve().parent / target
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")

        return payload


class _FakeCollector:
    def __init__(self, responses):
        self.responses = responses
        self.called = []

    def collect_game_events(self, game_id, event_type=None):
        self.called.append(game_id)
        return self.responses.get(
            game_id,
            {"game_id": game_id, "sources_checked": 0, "articles_found": 0, "hotspots": []},
        )


def run_selftest() -> int:
    fake_collector = _FakeCollector(
        {
            "GMHY-ZZ": {
                "game_id": "GMHY-ZZ",
                "sources_checked": 4,
                "articles_found": 4,
                "hotspots": [
                    {
                        "game_id": "GMHY-ZZ",
                        "game_name": "绝区零",
                        "event_type": "version_update",
                        "hotspot_score": 70,
                        "importance": "高",
                        "recommended_sources": [
                            {"source_name": "官网A", "source_type": "官网", "url": "https://a", "priority": 100, "fetch_method": "HTML"}
                        ],
                    },
                    {
                        "game_id": "GMHY-ZZ",
                        "game_name": "绝区零",
                        "event_type": "version_update",
                        "hotspot_score": 65,
                        "importance": "中",
                        "recommended_sources": [
                            {"source_name": "社区B", "source_type": "官方社区", "url": "https://b", "priority": 90, "fetch_method": "API"}
                        ],
                    },
                    {
                        "game_id": "GMHY-ZZ",
                        "game_name": "绝区零",
                        "event_type": "activity",
                        "hotspot_score": 65,
                        "importance": "中",
                        "recommended_sources": [
                            {"source_name": "官网A", "source_type": "官网", "url": "https://a", "priority": 100, "fetch_method": "HTML"}
                        ],
                    },
                    {
                        "game_id": "GMHY-ZZ",
                        "game_name": "绝区零",
                        "event_type": None,
                        "hotspot_score": 0,
                        "importance": None,
                        "recommended_sources": [],
                    },
                ],
            },
            "GMHY-YS": {
                "game_id": "GMHY-YS",
                "sources_checked": 2,
                "articles_found": 1,
                "hotspots": [
                    {
                        "game_id": "GMHY-YS",
                        "game_name": "原神",
                        "event_type": "character_release",
                        "hotspot_score": 65,
                        "importance": "高",
                        "recommended_sources": [
                            {"source_name": "官网YS", "source_type": "官网", "url": "https://ys", "priority": 100, "fetch_method": "HTML"}
                        ],
                    }
                ],
            },
        }
    )
    aggregator = GamingAggregator(collector=fake_collector)
    temp_path = Path(tempfile.gettempdir()) / "gaming_hotspots_selftest.json"

    try:
        payload = aggregator.aggregate(output_path=temp_path)
        written = json.loads(temp_path.read_text(encoding="utf-8"))
        ok = (
            payload["total_games"] == 129
            and payload["checked_games"] == 129
            and payload["failed_games"] == 0
            and payload["sources_checked"] == 6
            and payload["articles_found"] == 5
            and payload["hotspot_count"] == 3
            and payload["hotspots"][0]["game_id"] == "GMHY-ZZ"
            and payload["hotspots"][0]["game_name"] == "绝区零"
            and payload["hotspots"][0]["event_type"] == "version_update"
            and payload["hotspots"][0]["hotspot_score"] == 70
            and payload["hotspots"][0]["articles_count"] == 2
            and payload["hotspots"][0]["importance"] == "高"
            and payload["hotspots"][0]["recommended_sources"]
            == [{"source_name": "官网A", "source_type": "官网", "url": "https://a", "priority": 100, "fetch_method": "HTML"}]
            and all(hotspot.get("articles_count") for hotspot in payload["hotspots"])
            and all(
                {"game_id", "game_name", "event_type", "hotspot_score", "importance", "recommended_sources", "articles_count"}.issubset(
                    hotspot.keys()
                )
                for hotspot in payload["hotspots"]
            )
            and all(
                not (hotspot["event_type"] is None and (hotspot["hotspot_score"] or 0) <= 0)
                for hotspot in payload["hotspots"]
            )
            and written == payload
            and len(fake_collector.called) == 129
            and len(set(fake_collector.called)) == 128
        )
    finally:
        temp_path.unlink(missing_ok=True)

    summary = {
        "total_games": payload["total_games"],
        "checked_games": payload["checked_games"],
        "sources_checked": payload["sources_checked"],
        "articles_found": payload["articles_found"],
        "hotspot_count": payload["hotspot_count"],
        "top_hotspots": payload["hotspots"][:2],
    }
    print(f"[{'PASS' if ok else 'FAIL'}] 聚合 mock: {json.dumps(summary, ensure_ascii=False)}")
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gaming hotspot aggregator")
    parser.add_argument("--event-type", help="可选事件类型过滤")
    parser.add_argument("--output", help=f"输出路径（默认 {DEFAULT_OUTPUT}）")
    parser.add_argument("--registry", help="自定义注册表 JSON 路径")
    parser.add_argument("--selftest", action="store_true", help="运行内置 mock 验证")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    aggregator = GamingAggregator(registry_path=args.registry)
    payload = aggregator.aggregate(event_type=args.event_type, output_path=args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
