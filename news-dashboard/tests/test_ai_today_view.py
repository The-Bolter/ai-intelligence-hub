import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_today_view import BACKFILL_PENALTY, _decorate_article, _today_priority_score, build_ai_today_view


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def article(item_id, content_type, category, source, published, *, github=False, github_score=0, last_push=None,
            value_score=None, title=None, source_quality="high"):
    default_titles = {
        "model_update": "Major model release with new reasoning benchmark",
        "product_update": "Major version launch introduces core capability",
        "tech_direction": "Industry adoption trend changes the AI roadmap",
        "market_change": "Industry market shift and adoption trend",
        "tool": "High value AI tool",
    }
    item = {
        "id": item_id,
        "title": title or default_titles.get(category, item_id),
        "summary": item_id,
        "source": "github" if github else "rss",
        "source_name": source,
        "source_type": "github" if github else "rss",
        "source_quality": source_quality,
        "published": published,
        "content_type": content_type,
        "category": category,
        "value_score": (70 if not github else 20) if value_score is None else value_score,
        "final_score": 100,
    }
    if github:
        item["github_score"] = github_score
        item["metadata"] = {"last_push": last_push, "stars": 1000, "forks": 100}
    return item


class AiTodayViewTests(unittest.TestCase):
    def test_sections_and_source_isolation(self):
        items = [
            article("update-1", "updates", "model_update", "Source A", "2026-08-28T10:00:00+00:00"),
            article("update-2", "updates", "product_update", "Source B", "2026-08-28T09:00:00+00:00"),
            article("trend-1", "trend", "tech_direction", "Source C", "2026-08-28T08:00:00+00:00"),
            article("resource-1", "resources", "tool", "Source D", "2026-08-28T07:00:00+00:00"),
            article("gh-1", "resources", "tool", "GitHub", "2026-08-28T11:00:00+00:00", github=True,
                    github_score=95, last_push="2026-08-27T10:00:00+00:00"),
        ]
        original = copy.deepcopy(items)
        view = build_ai_today_view(items, NOW)
        self.assertEqual(len(view["today_priority"]), 4)
        self.assertGreaterEqual(sum(x["content_type"] == "updates" for x in view["today_priority"]), 2)
        self.assertGreaterEqual(sum(x["content_type"] == "trend" for x in view["today_priority"]), 1)
        self.assertFalse(any(x["source_type"] == "github" for x in view["today_priority"]))
        self.assertFalse(any(x["source_type"] == "github" for x in view["resources"]))
        self.assertEqual(len(view["resources"]), 1)
        self.assertEqual([x["id"] for x in view["github_radar"]], ["gh-1"])
        self.assertEqual(items, original)

    def test_today_backfills_48_hours_when_today_is_short(self):
        items = [
            article("today-update", "updates", "product_update", "Today", "2026-08-28T08:00:00+00:00"),
            article("old-update", "updates", "model_update", "Yesterday", "2026-08-27T10:00:00+00:00"),
            article("old-trend", "trend", "market_change", "Trend Source", "2026-08-27T09:00:00+00:00"),
            article("too-old", "trend", "tech_direction", "Old Source", "2026-08-25T10:00:00+00:00"),
        ]
        view = build_ai_today_view(items, NOW)
        ids = {x["id"] for x in view["today_priority"]}
        self.assertIn("old-update", ids)
        self.assertIn("old-trend", ids)
        self.assertNotIn("too-old", ids)

    def test_future_timestamp_is_clamped(self):
        future = article("future", "updates", "product_update", "Future", "2026-08-28T13:00:00+00:00")
        now_score = build_ai_today_view([future], NOW)["today_priority"][0]["today_priority_score"]
        current = article("current", "updates", "product_update", "Current", "2026-08-28T12:00:00+00:00")
        current_score = build_ai_today_view([current], NOW)["today_priority"][0]["today_priority_score"]
        self.assertEqual(now_score, current_score)

    def test_low_quality_product_and_trend_are_rejected_but_major_product_passes(self):
        items = [
            article("free", "updates", "product_update", "Marketing", "2026-08-28T11:00:00+00:00",
                    value_score=80, title="Product adds a free tier to attract more customers"),
            article("weak-trend", "trend", "market_change", "Weak", "2026-08-28T10:00:00+00:00",
                    value_score=29, title="AI company shares a routine update"),
            article("major-product", "updates", "product_update", "Product Source", "2026-08-28T09:00:00+00:00",
                    value_score=60, title="Major v2 launch introduces core capability"),
        ]
        ids = {x["id"] for x in build_ai_today_view(items, NOW)["today_priority"]}
        self.assertNotIn("free", ids)
        self.assertNotIn("weak-trend", ids)
        self.assertIn("major-product", ids)

    def test_community_source_needs_high_value_signal(self):
        items = [
            article("hn-weak", "updates", "breakthrough", "Hacker News", "2026-08-28T11:00:00+00:00",
                    value_score=59, title="Study reports a routine result"),
            article("hn-strong", "updates", "breakthrough", "Hacker News", "2026-08-28T10:00:00+00:00",
                    value_score=70, title="Breakthrough study reaches state-of-the-art benchmark"),
        ]
        ids = {x["id"] for x in build_ai_today_view(items, NOW)["today_priority"]}
        self.assertNotIn("hn-weak", ids)
        self.assertIn("hn-strong", ids)

    def test_cached_translation_wins_and_card_structure_is_preserved(self):
        item = article("cached", "updates", "product_update", "Source", "2026-08-28T11:00:00+00:00",
                       value_score=70, title="English product launch")
        item["chinese_summary"] = "[产品动态] | 核心信息: English fallback | 行业影响: 该动态为行业领域提供了新视角"
        decorated = _decorate_article(item, {
            "cached": {"title_cn": "中文产品发布", "summary_cn": "该产品上线核心能力并扩大可用范围"}
        })
        self.assertEqual(decorated["title_cn"], "中文产品发布")
        self.assertIn("该产品上线核心能力", decorated["core_info"])
        self.assertIn("核心信息:", decorated["card_summary"])
        self.assertNotIn("该动态为行业领域提供了新视角", decorated["card_summary"])

    def test_malformed_generated_core_falls_back_to_article_summary(self):
        item = article("malformed", "updates", "product_update", "Source", "2026-08-28T11:00:00+00:00",
                       value_score=70, title="Major version launch")
        item["summary"] = "The platform released version 2.0 with a rebuilt workflow. New capabilities are available."
        item["chinese_summary"] = "[产品动态] | 核心信息: 0 of its platform, its largest release"
        decorated = _decorate_article(item, {})
        self.assertTrue(decorated["core_info"].startswith("The platform released version 2.0"))

    def test_placeholder_summary_is_hidden_from_core_info(self):
        item = article("placeholder", "updates", "product_update", "Source", "2026-08-28T11:00:00+00:00",
                       value_score=70)
        item["summary"] = "点击查看原文>"
        item["chinese_summary"] = "[综合资讯] | 点击查看原文> | 行业影响: 该动态为行业领域提供了新视角"
        decorated = _decorate_article(item, {})
        self.assertEqual(decorated["core_info"], "")
        self.assertEqual(decorated["industry_impact"], "")

    def test_empty_generic_impact_is_not_generated(self):
        from fetcher import _chinese_summary
        result = _chinese_summary("An article", "An article without a mapped type.", [], ["综合资讯"])
        self.assertNotIn("该动态为行业领域提供了新视角", result)

    def test_category_and_content_type_caps(self):
        items = [
            article(f"model-{n}", "updates", "model_update", f"Model {n}", f"2026-08-28T{11-n:02d}:00:00+00:00")
            for n in range(4)
        ]
        items += [
            article("p1", "updates", "product_update", "P1", "2026-08-28T06:00:00+00:00"),
            article("p2", "updates", "product_update", "P2", "2026-08-28T05:00:00+00:00"),
            article("trend", "trend", "tech_direction", "Trend", "2026-08-28T04:00:00+00:00"),
        ]
        result = build_ai_today_view(items, NOW)["today_priority"]
        self.assertLessEqual(max(sum(x["category"] == c for x in result) for c in {x["category"] for x in result}), 2)
        self.assertLessEqual(max(sum(x["content_type"] == c for x in result) for c in {x["content_type"] for x in result}), 3)

    def test_backfill_is_second_stage_and_penalized(self):
        items = [
            article("today", "updates", "product_update", "Today", "2026-08-28T10:00:00+00:00", value_score=50),
            article("old-1", "updates", "breakthrough", "Old 1", "2026-08-27T10:00:00+00:00", value_score=80),
            article("old-2", "trend", "market_change", "Old 2", "2026-08-27T09:00:00+00:00", value_score=80),
            article("old-3", "updates", "model_update", "Old 3", "2026-08-27T08:00:00+00:00", value_score=80),
        ]
        result = build_ai_today_view(items, NOW)["today_priority"]
        self.assertEqual(result[0]["id"], "today")
        self.assertLessEqual(sum(x["id"].startswith("old-") for x in result), 2)
        baseline = {old["id"]: _today_priority_score(old, NOW) for old in items[1:]}
        self.assertTrue(all(x["today_priority_score"] == round(baseline[x["id"]] - BACKFILL_PENALTY, 3)
                            for x in result if x["id"].startswith("old-")))

    def test_source_cap_and_radar_limit(self):
        items = [
            article("a", "updates", "model_update", "Same", "2026-08-28T11:00:00+00:00"),
            article("b", "updates", "product_update", "Same", "2026-08-28T10:00:00+00:00"),
            article("c", "trend", "tech_direction", "Other", "2026-08-28T09:00:00+00:00"),
        ]
        for n in range(8):
            items.append(article(f"gh-{n}", "resources", "tool", "GitHub", "2026-08-28T01:00:00+00:00",
                                 github=True, github_score=60 + n,
                                 last_push="2026-08-27T10:00:00+00:00"))
        view = build_ai_today_view(items, NOW)
        self.assertEqual(len(view["github_radar"]), 5)
        self.assertEqual(len({x["source_name"] for x in view["today_priority"]}), len(view["today_priority"]))
        self.assertNotIn("b", {x["id"] for x in view["today_priority"]})


if __name__ == "__main__":
    unittest.main()
