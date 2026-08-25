"""Gaming Pipeline orchestration layer.

Provides a unified entry for converting single or multiple articles into
hotspot results. It wires GameResolver, EventClassifier, SourceSelector, and
game_hotspot.build_article_hotspot together while keeping component instances
shared so the registry is not reloaded for every article.

Usage:
    python gaming_pipeline.py --title "绝区零2.8版本前瞻特别节目"
    python gaming_pipeline.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys

from event_classifier import EventClassifier
from game_hotspot import build_article_hotspot
from game_resolver import GameResolver
from source_selector import SourceSelector


class GamingPipeline:
    def __init__(self, registry_path=None):
        self.registry_path = registry_path
        self.resolver = GameResolver(registry_path)
        self.classifier = EventClassifier(registry_path, self.resolver)
        self.selector = SourceSelector(registry_path)

    def process_article(self, title, summary=None) -> dict:
        return build_article_hotspot(
            title,
            summary,
            self.registry_path,
            resolver=self.resolver,
            classifier=self.classifier,
            selector=self.selector,
        )

    def process_articles(self, articles) -> list[dict]:
        results = []
        for article in articles or []:
            item = article or {}
            title = item.get("title")
            if not title:
                continue
            hotspot = self.process_article(title, item.get("summary"))
            if not hotspot.get("matched"):
                continue
            result = {
                key: value
                for key, value in hotspot.items()
                if key != "matched"
            }
            result.setdefault("recommended_sources", [])
            result.setdefault("hotspot_score", 0)
            results.append(result)
        results.sort(key=lambda item: (-item["hotspot_score"], item["game_name"] or ""))
        return results


def process_article(title, summary=None, registry_path=None) -> dict:
    return GamingPipeline(registry_path).process_article(title, summary)


def process_articles(articles, registry_path=None) -> list[dict]:
    return GamingPipeline(registry_path).process_articles(articles)


REQUIRED_KEYS = {
    "matched",
    "game_id",
    "game_name",
    "event_type",
    "importance",
    "hotspot_score",
    "recommended_sources",
}


def run_selftest(pipeline: GamingPipeline) -> int:
    all_ok = True

    result = pipeline.process_article("绝区零2.8版本前瞻特别节目")
    ok = (
        result.get("matched") is True
        and result.get("game_id") == "GMHY-ZZ"
        and result.get("event_type") == "version_update"
        and result.get("importance") == "高"
        and result.get("hotspot_score") == 70
        and bool(result.get("recommended_sources"))
        and REQUIRED_KEYS.issubset(result.keys())
    )
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 版本前瞻单篇: {json.dumps(result, ensure_ascii=False)}")

    result = pipeline.process_article("原神新角色上线公告")
    ok = (
        result.get("matched") is True
        and result.get("game_id") == "GMHY-YS"
        and result.get("event_type") == "character_release"
        and result.get("importance") == "高"
        and result.get("hotspot_score") == 65
        and bool(result.get("recommended_sources"))
        and REQUIRED_KEYS.issubset(result.keys())
    )
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 新角色单篇: {json.dumps(result, ensure_ascii=False)}")

    result = pipeline.process_article("今天天气不错，适合休息")
    ok = (
        result.get("matched") is False
        and result.get("hotspot_score") == 0
        and result.get("recommended_sources") == []
        and REQUIRED_KEYS.issubset(result.keys())
    )
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 无关文本: {json.dumps(result, ensure_ascii=False)}")

    articles = [
        {"title": "原神新角色上线公告", "summary": ""},
        {"title": "绝区零2.8版本前瞻特别节目", "summary": ""},
        {"title": "今天天气不错，适合休息", "summary": ""},
    ]
    results = pipeline.process_articles(articles)
    ok = (
        len(results) == 2
        and results[0]["game_name"] == "绝区零"
        and results[0]["event_type"] == "version_update"
        and results[0]["hotspot_score"] == 70
        and results[0]["importance"] == "高"
        and bool(results[0]["recommended_sources"])
        and results[1]["game_name"] == "原神"
        and results[1]["event_type"] == "character_release"
        and results[1]["hotspot_score"] == 65
        and results[1]["importance"] == "高"
        and bool(results[1]["recommended_sources"])
    )
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 多篇排序: {json.dumps(results, ensure_ascii=False)}")

    return 0 if all_ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gaming Pipeline 统一入口")
    parser.add_argument("--title", help="标题文本")
    parser.add_argument("--summary", help="摘要文本")
    parser.add_argument("--registry", help="自定义注册表 JSON 路径")
    parser.add_argument("--selftest", action="store_true", help="运行内置 mock 验证")
    args = parser.parse_args(argv)

    pipeline = GamingPipeline(args.registry)
    if args.selftest:
        return run_selftest(pipeline)
    if args.title:
        print(json.dumps(pipeline.process_article(args.title, args.summary), ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
