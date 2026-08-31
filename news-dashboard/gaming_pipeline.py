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
from gaming_event_normalizer import normalize_event
from gaming_v2_rules import canonicalize_event_type
from game_hotspot import build_article_hotspot
from game_resolver import GameResolver
from source_selector import SourceSelector


class _LegacyClassifierAdapter:
    """Expose registry event types only to the existing Aggregator path."""

    def __init__(self, classifier):
        self.classifier = classifier

    def classify(self, *args, **kwargs):
        result = self.classifier.classify(*args, **kwargs)
        legacy_type = result.get("legacy_event_type")
        if result.get("matched") and legacy_type:
            result = dict(result)
            result["event_type"] = legacy_type
        return result


class GamingPipeline:
    def __init__(self, registry_path=None, resolver=None, classifier=None, selector=None):
        self.registry_path = registry_path
        self.resolver = resolver if resolver is not None else GameResolver(registry_path)
        self.classifier = (
            classifier
            if classifier is not None
            else EventClassifier(registry_path, self.resolver)
        )
        self.selector = selector if selector is not None else SourceSelector(registry_path)
        self._legacy_classifier = _LegacyClassifierAdapter(self.classifier)

    def process_article(self, title, summary=None) -> dict:
        return build_article_hotspot(
            title,
            summary,
            self.registry_path,
            resolver=self.resolver,
            classifier=self._legacy_classifier,
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

    def _normalize_one(self, article, reference_date=None):
        item = dict(article or {})
        title = item.get("title") or item.get("headline") or ""
        summary = item.get("summary") or item.get("content") or ""
        if not title:
            return None

        game = self.resolver.resolve(title, summary)
        if not game.get("matched"):
            if not item.get("game_id") or not item.get("game_name"):
                return None
            game = {
                "matched": True,
                "game_id": item["game_id"],
                "game_name": item["game_name"],
                "platforms": item.get("platforms") or [],
                "display_group": item.get("display_group"),
            }

        configured_event_type = canonicalize_event_type(item.get("event_type"), title)
        if configured_event_type:
            classification = {
                "matched": True,
                "event_type": configured_event_type,
                "event_name": item.get("event_name") or title,
            }
        else:
            classification = self.classifier.classify(
                title, summary, game_id=game.get("game_id")
            )
            if not classification.get("matched"):
                return None

        sources = item.get("recommended_sources")
        if not sources:
            sources = self.selector.select(
                game.get("game_id"), classification.get("event_type") or ""
            ).get("sources", [])
        event = normalize_event(
            item,
            game,
            classification,
            recommended_sources=sources,
            reference_date=reference_date,
        )
        if event is None:
            return None
        for key in ("game_scale", "game_scale_score", "game_attention"):
            value = item.get(key, game.get(key))
            if value not in (None, ""):
                event[key] = value
        event["source_articles"] = [item]
        return event

    def normalize_article(self, article, reference_date=None) -> dict:
        """Normalize one article into confirmed/pending event collections."""
        event = self._normalize_one(article, reference_date=reference_date)
        if event is None:
            return {"events": [], "pending": []}
        if event["event_id"] is None:
            return {"events": [], "pending": [event]}
        return {"events": [event], "pending": []}

    def normalize_articles(self, articles, reference_date=None) -> dict:
        """Normalize articles without changing the legacy hotspot methods."""
        result = {"events": [], "pending": []}
        for article in articles or []:
            normalized = self.normalize_article(article, reference_date=reference_date)
            result["events"].extend(normalized["events"])
            result["pending"].extend(normalized["pending"])
        return result


def process_article(title, summary=None, registry_path=None) -> dict:
    return GamingPipeline(registry_path).process_article(title, summary)


def process_articles(articles, registry_path=None) -> list[dict]:
    return GamingPipeline(registry_path).process_articles(articles)


def normalize_article(article, registry_path=None, reference_date=None) -> dict:
    return GamingPipeline(registry_path).normalize_article(article, reference_date=reference_date)


def normalize_articles(articles, registry_path=None, reference_date=None) -> dict:
    return GamingPipeline(registry_path).normalize_articles(articles, reference_date=reference_date)


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
