import json
import sys
import unittest
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_digest_v2 import (
    build_ai_digest,
    compose_home_feed,
    filter_by_channel,
    normalize_ai_article,
)


def article(
    item_id,
    title,
    category,
    source_name,
    score,
    *,
    github=False,
    stars=0,
):
    source = "github" if github else "rss"
    url = f"https://github.com/example/{item_id}" if github else f"https://example.com/{item_id}"
    return {
        "id": item_id,
        "title": title,
        "summary": f"Summary for {title}",
        "link": url,
        "source": source,
        "source_name": source_name,
        "source_type": source,
        "published": "2026-08-25T10:00:00+00:00",
        "category": category,
        "value_score": score,
        "final_score": score,
        "github_score": score if github else 0,
        "metadata": {"stars": stars, "topics": ["ai"] if github else []},
    }


class AiDigestV2Tests(unittest.TestCase):
    def diverse_articles(self):
        specs = [
            ("model_update", "New GPT model release"),
            ("product_update", "AI product adds a new feature"),
            ("agent", "Agent workflow automation"),
            ("breakthrough", "Research paper benchmark breakthrough"),
            ("company", "AI company funding and policy update"),
        ]
        items = []
        for group, (category, title) in enumerate(specs):
            for index in range(5):
                items.append(
                    article(
                        f"rss-{group}-{index}",
                        f"{title} {index}",
                        category,
                        f"Source-{group}-{index}",
                        90 - index,
                    )
                )
        for index in range(30):
            items.append(
                article(
                    f"gh-{index}",
                    f"example/repo-{index}",
                    "tool",
                    "GitHub",
                    100 - index,
                    github=True,
                    stars=50_000,
                )
            )
        return items

    def test_normalize_adds_v2_contract_fields(self):
        item = normalize_ai_article(
            article("m1", "New model release", "model_update", "Lab", 80)
        )
        self.assertEqual(item["channel"], "models")
        self.assertEqual(item["content_type"], "model_release")
        self.assertEqual(item["url"], item["link"])
        self.assertEqual(item["published_at"], item["published"])
        self.assertTrue(item["home_eligible"])
        self.assertFalse(item["is_github"])

    def test_home_feed_is_diverse_and_caps_github(self):
        result = compose_home_feed(self.diverse_articles(), limit=10)
        github_count = sum(1 for item in result if item["is_github"])
        channels = {item["channel"] for item in result}
        self.assertEqual(len(result), 10)
        self.assertLessEqual(github_count, 2)
        self.assertGreaterEqual(len(channels), 4)

    def test_channel_and_source_caps_are_hard_limits(self):
        result = compose_home_feed(self.diverse_articles(), limit=10)
        channel_counts = Counter(item["channel"] for item in result)
        source_counts = Counter(item["source_name"] for item in result)
        self.assertLessEqual(max(channel_counts.values()), 3)
        self.assertLessEqual(max(source_counts.values()), 3)

    def test_low_value_github_project_is_not_on_homepage(self):
        low_repo = article(
            "low-gh", "small/repo", "tool", "GitHub", 20, github=True, stars=50
        )
        result = compose_home_feed(
            [
                low_repo,
                article("p1", "AI product feature", "product_update", "News", 60),
            ],
            limit=5,
        )
        self.assertNotIn("low-gh", [item["id"] for item in result])

    def test_channel_filter_contains_only_requested_channel(self):
        result = filter_by_channel(self.diverse_articles(), "research")
        self.assertTrue(result)
        self.assertTrue(all(item["channel"] == "research" for item in result))

    def test_ranking_is_stable_when_input_order_changes(self):
        items = self.diverse_articles()
        first = compose_home_feed(items, limit=12)
        second = compose_home_feed(list(reversed(items)), limit=12)
        self.assertEqual(
            [item["id"] for item in first],
            [item["id"] for item in second],
        )

    def test_digest_and_sample_follow_schema(self):
        payload = build_ai_digest(
            self.diverse_articles(),
            generated_at="2026-08-25T12:00:00+00:00",
            limit=10,
        )
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(set(payload["guides"]), set(payload["channels"]))
        self.assertLessEqual(payload["stats"]["github_ratio"], 0.2)

        sample_path = Path(__file__).parent / "fixtures" / "ai_digest_v2_sample.json"
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        self.assertEqual(sample["schema_version"], 2)
        self.assertTrue(sample["items"])
        required = {
            "id", "title", "summary", "url", "published_at", "source_name",
            "source_type", "content_type", "channel", "value_score",
            "final_score", "home_eligible", "is_github",
        }
        self.assertTrue(required.issubset(sample["items"][0]))


if __name__ == "__main__":
    unittest.main()
