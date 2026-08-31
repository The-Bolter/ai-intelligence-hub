import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_today_view import build_ai_today_view


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def article(item_id, content_type, category, source, published, *, github=False, github_score=0, last_push=None):
    item = {
        "id": item_id,
        "title": item_id,
        "summary": item_id,
        "source": "github" if github else "rss",
        "source_name": source,
        "source_type": "github" if github else "rss",
        "source_quality": "high",
        "published": published,
        "content_type": content_type,
        "category": category,
        "value_score": 70 if not github else 20,
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
