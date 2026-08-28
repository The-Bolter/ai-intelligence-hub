"""Select official sources for a game and event type.

The selector loads sources and page mappings from config/game_registry.json.
It first filters the game's sources by URLs of page mappings whose page type
matches the event type, then falls back to all of the game's sources. Sources
are always sorted by priority descending.

Registry fields are mapped from the current Chinese headers:
    URL -> url, source_priority -> priority,
    抓取方式 -> fetch_method, 页面类型 -> page_type

Usage:
    python source_selector.py --game-id GMHY-YS --event-type version_update
    python source_selector.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_REGISTRY = Path(__file__).resolve().parent / "config" / "game_registry.json"

EVENT_PAGE_TYPES = {
    "major_update": ("公告", "版本", "更新"),
    "monthly_update": ("公告", "版本", "更新"),
    "weekly_update": ("公告", "版本", "更新"),
    "season_start": ("公告", "赛季", "活动"),
    "new_map": ("公告", "版本", "地图", "内容"),
    "new_character": ("公告", "版本", "角色", "内容"),
    "collaboration": ("公告", "联动", "活动"),
    "major_event": ("公告", "活动"),
    "test_or_launch": ("公告", "测试", "上线"),
    "version_update": ("公告", "版本"),
    "character_release": ("公告", "版本", "角色", "内容"),
    "activity": ("活动",),
    "esports": ("赛事",),
}


def _first(record: dict, *keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _to_int_priority(value) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if text in ("", "-"):
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


def _build_source(record: dict, order: int) -> dict:
    return {
        "game_id": _first(record, "game_id"),
        "source_name": _first(record, "source_name") or "",
        "source_type": _first(record, "source_type") or "",
        "url": _first(record, "URL", "url") or "",
        "priority": _to_int_priority(_first(record, "source_priority", "priority")),
        "fetch_method": _first(record, "抓取方式", "fetch_method") or "",
        "_order": order,
    }


def _build_page(record: dict) -> dict:
    return {
        "game_id": _first(record, "game_id"),
        "page_type": _first(record, "页面类型", "page_type") or "",
        "url": _first(record, "URL", "url") or "",
        "render_method": _first(record, "渲染方式", "render_method") or "",
    }


def _page_type_matches(event_type: str, page_type: str) -> bool:
    keywords = EVENT_PAGE_TYPES.get(event_type)
    if not keywords:
        return False
    return any(keyword in page_type for keyword in keywords)


class SourceSelector:
    def __init__(self, registry_path=None):
        self.registry_path = Path(registry_path) if registry_path else DEFAULT_REGISTRY
        self._sources_by_game: dict[str, list[dict]] = {}
        self._pages_by_game: dict[str, list[dict]] = {}
        self._load()

    def _load(self) -> None:
        if not self.registry_path.is_file():
            raise FileNotFoundError(f"游戏注册表不存在: {self.registry_path}")
        with self.registry_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        sources = data.get("sources", data.get("game_sources", []))
        pages = data.get("page_mappings", [])

        for order, record in enumerate(sources):
            source = _build_source(record, order)
            if source["game_id"]:
                self._sources_by_game.setdefault(source["game_id"], []).append(source)

        for record in pages:
            page = _build_page(record)
            if page["game_id"]:
                self._pages_by_game.setdefault(page["game_id"], []).append(page)

    def select(self, game_id, event_type) -> dict:
        game_id = game_id or ""
        event_type = event_type or ""
        sources = list(self._sources_by_game.get(game_id, []))
        if not sources:
            return {"game_id": game_id, "event_type": event_type, "sources": []}

        preferred_urls = {
            page["url"]
            for page in self._pages_by_game.get(game_id, [])
            if _page_type_matches(event_type, page["page_type"]) and page["url"]
        }
        selected = [source for source in sources if source["url"] and source["url"] in preferred_urls]
        if not selected:
            selected = sources

        selected.sort(key=lambda source: (-source["priority"], source["_order"]))
        output_sources = [
            {
                "source_name": source["source_name"],
                "source_type": source["source_type"],
                "url": source["url"],
                "priority": source["priority"],
                "fetch_method": source["fetch_method"],
            }
            for source in selected
        ]
        return {"game_id": game_id, "event_type": event_type, "sources": output_sources}


def run_selftest(selector: SourceSelector) -> int:
    all_ok = True

    result = selector.select("GMHY-YS", "version_update")
    ok = (
        bool(result["sources"])
        and result["sources"][0]["url"] == "https://ys.mihoyo.com/main/news"
        and result["sources"][0]["priority"] == 100
    )
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 版本更新事件: {json.dumps(result, ensure_ascii=False)}")

    result = selector.select("GMHY-YS", "activity")
    all_count = len(selector._sources_by_game.get("GMHY-YS", []))
    priorities = [source["priority"] for source in result["sources"]]
    ok = (
        bool(result["sources"])
        and len(result["sources"]) == all_count
        and priorities == sorted(priorities, reverse=True)
    )
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 活动开启事件: {json.dumps(result, ensure_ascii=False)}")

    result = selector.select("GAME-NOT-EXIST", "version_update")
    ok = result["sources"] == []
    all_ok = all_ok and ok
    print(f"[{'PASS' if ok else 'FAIL'}] 不存在游戏: {json.dumps(result, ensure_ascii=False)}")

    return 0 if all_ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="根据 game_id 和 event_type 选择官方信息源")
    parser.add_argument("--game-id", help="游戏 ID")
    parser.add_argument("--event-type", help="事件类型")
    parser.add_argument("--registry", help="自定义注册表 JSON 路径")
    parser.add_argument("--selftest", action="store_true", help="运行内置 mock 验证")
    args = parser.parse_args(argv)

    selector = SourceSelector(args.registry)
    if args.selftest:
        return run_selftest(selector)
    if not args.game_id or not args.event_type:
        parser.error("--game-id 和 --event-type 必填")
    result = selector.select(args.game_id, args.event_type)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
