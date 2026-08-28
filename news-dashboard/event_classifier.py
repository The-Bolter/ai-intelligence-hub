"""Classify game operation event types from title/summary text.

The classifier loads event rules from config/game_registry.json and matches
them against text using regex rules. It is rule-based and does not call any
AI model. When no game_id is supplied, it uses game_resolver.GameResolver to
resolve the game first, then prefers that game's rules before global rules.

Registry fields are mapped from the current Chinese headers:
    事件中文 -> event_name, 关键词(正则) -> regex_pattern,
    匹配逻辑 -> match_logic, 重要程度 -> importance

Usage:
    python event_classifier.py --title "绝区零2.8版本前瞻特别节目"
    python event_classifier.py --selftest
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from game_resolver import GameResolver
from gaming_v2_rules import canonicalize_event_type

DEFAULT_REGISTRY = Path(__file__).resolve().parent / "config" / "game_registry.json"

_RULE_FIELDS = {
    "game_id": ("game_id",),
    "event_type": ("event_type",),
    "event_name": ("event_name", "事件中文"),
    "regex_pattern": ("regex_pattern", "关键词(正则)"),
    "match_logic": ("match_logic", "匹配逻辑"),
    "importance": ("importance", "重要程度"),
    "example": ("example", "示例"),
}

_IMPORTANCE_RANK = {"高": 3, "中": 2, "低": 1}
_AND_LOGIC = {"AND", "且", "并且", "全部"}


def _first(record: dict, key: str):
    for candidate in _RULE_FIELDS[key]:
        value = record.get(candidate)
        if value not in (None, ""):
            return value
    return None


def _split_patterns(value) -> list[str]:
    if value is None:
        return []
    parts = str(value).splitlines()
    return [part.strip() for part in parts if part.strip()]


def _normalize_logic(value) -> str:
    if value is None:
        return "OR"
    normalized = str(value).strip().upper()
    return "AND" if normalized in _AND_LOGIC else "OR"


def _build_rule(record: dict, order: int) -> dict:
    patterns = []
    for raw in _split_patterns(_first(record, "regex_pattern")):
        try:
            patterns.append(re.compile(raw, re.IGNORECASE))
        except re.error:
            continue
    return {
        "game_id": _first(record, "game_id"),
        "event_type": _first(record, "event_type"),
        "event_name": _first(record, "event_name"),
        "importance": _first(record, "importance"),
        "example": _first(record, "example"),
        "match_logic": _normalize_logic(_first(record, "match_logic")),
        "pattern_text": _first(record, "regex_pattern") or "",
        "patterns": patterns,
        "order": order,
    }


def _rule_matches(rule: dict, texts: list[str]) -> bool:
    if not rule["patterns"]:
        return False
    for text in texts:
        if rule["match_logic"] == "AND":
            if all(pattern.search(text) for pattern in rule["patterns"]):
                return True
        elif any(pattern.search(text) for pattern in rule["patterns"]):
            return True
    return False


class EventClassifier:
    def __init__(self, registry_path=None, resolver: GameResolver | None = None):
        self.registry_path = Path(registry_path) if registry_path else DEFAULT_REGISTRY
        self.rules = self._load_rules()
        self.resolver = resolver if resolver is not None else GameResolver(self.registry_path)

    def _load_rules(self) -> list[dict]:
        if not self.registry_path.is_file():
            raise FileNotFoundError(f"游戏注册表不存在: {self.registry_path}")
        with self.registry_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [
            _build_rule(record, order)
            for order, record in enumerate(data.get("event_rules", []))
        ]

    def classify(self, title, summary=None, game_id=None) -> dict:
        texts = [str(item) for item in (title, summary) if item]
        if not texts:
            return self._no_match()

        resolved_game_id = game_id
        if resolved_game_id is None and self.resolver is not None:
            resolved = self.resolver.resolve(title, summary)
            if resolved.get("matched"):
                resolved_game_id = resolved.get("game_id")

        game_matches = []
        global_matches = []
        for rule in self.rules:
            if not _rule_matches(rule, texts):
                continue
            if rule["game_id"]:
                if resolved_game_id is not None and rule["game_id"] == resolved_game_id:
                    game_matches.append(rule)
            else:
                global_matches.append(rule)

        group = game_matches or global_matches
        if not group:
            return self._no_match()

        best = min(
            group,
            key=lambda rule: (
                -(rule["game_id"] is not None),
                -_IMPORTANCE_RANK.get(rule["importance"], 0),
                rule["order"],
            ),
        )
        confidence = 100 if best["game_id"] else 90
        event_name = best["event_name"] or best["event_type"]
        canonical_event_type = canonicalize_event_type(
            best["event_type"], " ".join(texts)
        )
        if canonical_event_type is None:
            return self._no_match()
        return {
            "matched": True,
            "event_type": canonical_event_type,
            "event_name": event_name,
            "importance": best["importance"],
            "matched_rule": event_name or best["pattern_text"],
            "confidence": confidence,
            "legacy_event_type": best["event_type"],
        }

    @staticmethod
    def _no_match() -> dict:
        return {
            "matched": False,
            "event_type": None,
            "event_name": None,
            "importance": None,
            "matched_rule": None,
            "confidence": 0,
            "legacy_event_type": None,
        }


SELF_TESTS = [
    ("版本前瞻识别", "绝区零2.8版本前瞻特别节目", None, None, {"matched": True, "event_type": "monthly_update", "event_name": "版本更新"}),
    ("新角色识别", "原神新角色上线公告", None, None, {"matched": True, "event_type": "new_character"}),
    ("赛事识别", "英雄联盟全球总决赛开启", None, None, {"matched": True, "event_type": "esports"}),
    ("无事件文本", "今天吃什么", None, None, {"matched": False}),
]


def run_selftest(classifier: EventClassifier) -> int:
    all_ok = True
    for label, title, summary, game_id, expected in SELF_TESTS:
        result = classifier.classify(title, summary, game_id)
        ok = all(result.get(key) == value for key, value in expected.items())
        all_ok = all_ok and ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {label}: {json.dumps(result, ensure_ascii=False)}")
    return 0 if all_ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="根据热点文本识别游戏运营事件")
    parser.add_argument("--title", help="标题文本")
    parser.add_argument("--summary", help="摘要文本")
    parser.add_argument("--game-id", help="可选游戏 ID")
    parser.add_argument("--registry", help="自定义注册表 JSON 路径")
    parser.add_argument("--selftest", action="store_true", help="运行内置 mock 验证")
    args = parser.parse_args(argv)

    classifier = EventClassifier(args.registry)
    if args.selftest:
        return run_selftest(classifier)
    if args.title:
        print(json.dumps(classifier.classify(args.title, args.summary, args.game_id), ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
