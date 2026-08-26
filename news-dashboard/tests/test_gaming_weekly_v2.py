from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gaming_weekly_v2 import (  # noqa: E402
    build_game_weekly_v2,
    classify_event_type,
    filter_events_by_type,
    natural_week,
    write_game_weekly_v2,
)


REFERENCE = datetime.fromisoformat("2026-08-26T12:00:00+08:00")


def article(title, game="原神", url="https://example.com/news/1", **overrides):
    item = {
        "id": url.rsplit("/", 1)[-1],
        "title": title,
        "summary": title,
        "game_entity": game,
        "link": url,
        "source": "Example Gaming",
        "published": "2026-08-25T10:00:00+08:00",
        "game_attention": 12,
    }
    item.update(overrides)
    return item


class GamingWeeklyV2Tests(unittest.TestCase):
    def test_distinguishes_four_update_cadences(self):
        cases = {
            "4.5 Major Update launches August 26, 2026": "major_update",
            "Monthly Update arrives August 26, 2026": "monthly_update",
            "Weekly Update arrives August 26, 2026": "weekly_update",
            "Season 8 starts August 26, 2026": "season_start",
        }
        self.assertEqual(
            {classify_event_type(article(title)) for title in cases},
            set(cases.values()),
        )
        for title, expected in cases.items():
            self.assertEqual(classify_event_type(article(title)), expected)

    def test_classifies_remaining_stable_event_types(self):
        cases = {
            "New map arrives August 26, 2026": "new_map",
            "New character Alice arrives August 26, 2026": "new_character",
            "Collaboration with Example starts August 26, 2026": "collaboration",
            "Anniversary event starts August 26, 2026": "major_event",
            "Global launch begins August 26, 2026": "test_or_launch",
            "World finals begin August 26, 2026": "esports",
        }
        for title, expected in cases.items():
            self.assertEqual(classify_event_type(article(title)), expected)

    def test_multiple_sources_for_same_event_are_merged_and_official_wins(self):
        items = [
            article(
                "Version 4.5 Major Update launches August 26, 2026",
                url="https://media.example/report",
                summary="Secondary report.",
            ),
            article(
                "Version 4.5 Major Update launches August 26, 2026",
                url="https://game.example/official",
                source="游戏官方公告",
                official=True,
                source_priority=100,
                summary="Official 4.5 release announcement.",
            ),
        ]
        payload = build_game_weekly_v2(items, REFERENCE)
        self.assertEqual(len(payload["events"]), 1)
        event = payload["events"][0]
        self.assertEqual(len(event["sources"]), 2)
        self.assertTrue(event["sources"][0]["official"])
        self.assertEqual(event["summary"], "Official 4.5 release announcement.")

    def test_same_day_different_games_never_merge(self):
        items = [
            article("Version 4.5 Major Update launches 2026-08-26", game="原神", url="https://a.example/1"),
            article("Version 4.5 Major Update launches 2026-08-26", game="崩坏：星穹铁道", url="https://b.example/1"),
        ]
        payload = build_game_weekly_v2(items, REFERENCE)
        self.assertEqual(len(payload["events"]), 2)
        self.assertEqual({event["game"] for event in payload["events"]}, {"原神", "崩坏：星穹铁道"})

    def test_week_boundaries_across_month_and_year(self):
        self.assertEqual(tuple(map(str, natural_week("2026-09-01T01:00:00+08:00"))), ("2026-08-31", "2026-09-06"))
        self.assertEqual(tuple(map(str, natural_week("2027-01-01T12:00:00+08:00"))), ("2026-12-28", "2027-01-03"))

        items = [
            article("Weekly Update August 24, 2026", url="https://a.example/start"),
            article("Weekly Update August 30, 2026", url="https://a.example/end"),
            article("Weekly Update August 31, 2026", url="https://a.example/out"),
        ]
        payload = build_game_weekly_v2(items, REFERENCE)
        self.assertEqual([event["event_date"] for event in payload["events"]], ["2026-08-24", "2026-08-30"])

    def test_unconfirmed_date_is_excluded(self):
        payload = build_game_weekly_v2(
            [article("Major Update announced", published="2026-08-26T08:00:00+08:00")],
            REFERENCE,
        )
        self.assertEqual(payload["events"], [])

    def test_heat_score_equals_factors_and_is_capped(self):
        item = article(
            "Version 9.0 Major Update launches August 26, 2026",
            official=True,
            game_attention=999,
        )
        event = build_game_weekly_v2([item], REFERENCE)["events"][0]
        self.assertEqual(event["heat_score"], sum(event["heat_factors"].values()))
        self.assertLessEqual(event["heat_score"], 100)
        self.assertLessEqual(event["heat_factors"]["game_attention"], 15)

    def test_filter_uses_real_event_type(self):
        items = [
            article("Weekly Update August 26, 2026", url="https://a.example/weekly"),
            article("Season 9 starts August 27, 2026", url="https://a.example/season"),
        ]
        payload = build_game_weekly_v2(items, REFERENCE)
        filtered = filter_events_by_type(payload, "season_start")
        self.assertEqual(len(filtered), 1)
        self.assertTrue(all(event["event_type"] == "season_start" for event in filtered))
        with self.assertRaises(ValueError):
            filter_events_by_type(payload, "unknown")

    def test_contract_fields_and_chinese_yearless_date(self):
        payload = build_game_weekly_v2(
            [article("4.5 大版本将于8月26日强制更新", official=True)],
            REFERENCE,
        )
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["timezone"], "Asia/Shanghai")
        event = payload["events"][0]
        self.assertEqual(event["version"], "4.5")
        self.assertEqual(
            set(event),
            {"id", "game", "event_date", "event_type", "version", "headline", "summary", "heat_score", "heat_factors", "sources", "updated_at"},
        )

    def test_writer_creates_contract_json(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "game_weekly_v2.json"
            expected = write_game_weekly_v2(
                [article("Weekly Update August 26, 2026")],
                output_path=output_path,
                reference_time=REFERENCE,
            )
            self.assertTrue(output_path.is_file())
            self.assertEqual(output_path.read_text(encoding="utf-8").count('"schema_version": 2'), 1)
            self.assertEqual(expected["events"][0]["event_type"], "weekly_update")


if __name__ == "__main__":
    unittest.main()
