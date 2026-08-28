"""Resolve games from hot-topic text using rule-based matching.

The resolver reads config/game_registry.json and matches game names, aliases,
and vendors against title/summary text. It is intentionally rule-based and
does not call any AI model.

Registry fields are mapped from the current Chinese headers:
    游戏名称 -> name_cn, 英文名称 -> name_en,
    别名/缩写 -> aliases, 厂商/发行商 -> vendor

Usage:
    python game_resolver.py --title "绝区零2.8版本更新公告"
    python game_resolver.py --selftest
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_REGISTRY = Path(__file__).resolve().parent / "config" / "game_registry.json"

_FIELD_ALIASES = {
    "game_id": ("game_id",),
    "name_cn": ("name_cn", "游戏名称"),
    "name_en": ("name_en", "英文名称"),
    "aliases": ("aliases", "别名/缩写"),
    "vendor": ("vendor", "厂商/发行商"),
    "platforms": ("platforms", "平台"),
    "display_group": ("display_group",),
}

_ALIAS_SEPARATORS = re.compile(r"[,，、;；/|｜\n]+")
_WHITESPACE = re.compile(r"[\s\u3000]+")

_NAME_CONFIDENCE = 100
_ALIAS_CONFIDENCE = 85
_VENDOR_CONFIDENCE = 65
_MIN_MATCH_LENGTH = 2


def _normalize(value: str) -> str:
    return _WHITESPACE.sub("", value.strip()).lower()


def _first(record: dict, key: str):
    for candidate in _FIELD_ALIASES[key]:
        value = record.get(candidate)
        if value not in (None, ""):
            return value
    return None


def _split_aliases(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        parts = [str(item) for item in value if item not in (None, "")]
    else:
        parts = _ALIAS_SEPARATORS.split(str(value))
    return [part.strip() for part in parts if part.strip()]


def _parse_platforms(value) -> list[str]:
    values = value if isinstance(value, list) else _ALIAS_SEPARATORS.split(str(value or ""))
    text = " ".join(str(item).casefold() for item in values)
    platforms = []
    if any(token in text for token in ("mobile", "android", "ios", "手游", "移动端")):
        platforms.append("mobile")
    if any(token in text for token in (
        "pc", "windows", "mac", "linux", "steam", "playstation", "ps4", "ps5",
        "xbox", "switch", "console", "主机", "端游",
    )):
        platforms.append("pc")
    return platforms


def _display_group(value, platforms: list[str]) -> str:
    explicit = str(value or "").strip().casefold()
    if explicit in ("mobile", "pc"):
        return explicit
    return "mobile" if "mobile" in platforms else "pc"


def _build_entry(record: dict) -> dict:
    platforms = _parse_platforms(_first(record, "platforms"))
    return {
        "game_id": _first(record, "game_id"),
        "name_cn": _first(record, "name_cn"),
        "name_en": _first(record, "name_en"),
        "vendor": _first(record, "vendor"),
        "aliases": _split_aliases(_first(record, "aliases")),
        "platforms": platforms,
        "display_group": _display_group(_first(record, "display_group"), platforms),
    }


def _contains(text: str, value) -> bool:
    if value is None:
        return False
    normalized = _normalize(str(value))
    return len(normalized) >= _MIN_MATCH_LENGTH and normalized in text


def _score_entry(entry: dict, texts: list[str]) -> tuple | None:
    best = None
    for text in texts:
        normalized_text = _normalize(text)
        checks = [
            (_NAME_CONFIDENCE, "name", entry["name_cn"]),
            (_NAME_CONFIDENCE, "name", entry["name_en"]),
        ]
        for alias in entry["aliases"]:
            checks.append((_ALIAS_CONFIDENCE, "alias", alias))
        checks.append((_VENDOR_CONFIDENCE, "vendor", entry["vendor"]))

        for confidence, match_type, value in checks:
            if not _contains(normalized_text, value):
                continue
            candidate = (confidence, match_type, str(value))
            if best is None or candidate[0] > best[0] or (
                candidate[0] == best[0] and len(candidate[2]) > len(best[2])
            ):
                best = candidate
    return best


class GameResolver:
    def __init__(self, registry_path=None):
        self.registry_path = Path(registry_path) if registry_path else DEFAULT_REGISTRY
        self.games = self._load_games()

    def _load_games(self) -> list[dict]:
        if not self.registry_path.is_file():
            raise FileNotFoundError(f"游戏注册表不存在: {self.registry_path}")
        with self.registry_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        games = []
        for record in data.get("games", []):
            entry = _build_entry(record)
            if entry["game_id"]:
                games.append(entry)
        return games

    def resolve(self, title, summary=None) -> dict:
        texts = [str(item) for item in (title, summary) if item]
        if not texts:
            return self._no_match()

        candidates = []
        for entry in self.games:
            score = _score_entry(entry, texts)
            if score is None:
                continue
            confidence, match_type, matched_value = score
            candidates.append(
                {
                    "entry": entry,
                    "confidence": confidence,
                    "match_type": match_type,
                    "matched_value": matched_value,
                }
            )

        if not candidates:
            return self._no_match()

        candidates.sort(
            key=lambda item: (
                -item["confidence"],
                -len(item["matched_value"]),
                item["entry"]["game_id"] or "",
            )
        )
        best = candidates[0]
        entry = best["entry"]
        return {
            "matched": True,
            "game_id": entry["game_id"],
            "game_name": entry["name_cn"] or entry["name_en"],
            "match_type": best["match_type"],
            "confidence": best["confidence"],
            "platforms": list(entry["platforms"]),
            "display_group": entry["display_group"],
        }

    @staticmethod
    def _no_match() -> dict:
        return {
            "matched": False,
            "game_id": None,
            "game_name": None,
            "match_type": None,
            "confidence": 0,
            "platforms": [],
            "display_group": None,
        }


SELF_TESTS = [
    ("正确游戏命中", "绝区零2.8版本更新公告", None, {"matched": True, "match_type": "name", "game_name": "绝区零"}),
    ("别名命中", "ZZZ 新活动预告", None, {"matched": True, "match_type": "alias", "game_name": "绝区零"}),
    ("无游戏文本", "今天天气不错，适合休息", None, {"matched": False}),
    ("多游戏文本", "原神和绝区零同时开启新版本", None, {"matched": True, "game_name": "绝区零"}),
    ("厂商命中", "米哈游发布新版本更新公告", None, {"matched": True, "match_type": "vendor"}),
]


def run_selftest(resolver: GameResolver) -> int:
    all_ok = True
    for label, title, summary, expected in SELF_TESTS:
        result = resolver.resolve(title, summary)
        ok = all(result.get(key) == value for key, value in expected.items())
        all_ok = all_ok and ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {label}: {json.dumps(result, ensure_ascii=False)}")
    return 0 if all_ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="根据热点文本识别游戏")
    parser.add_argument("--title", help="标题文本")
    parser.add_argument("--summary", help="摘要文本")
    parser.add_argument("--selftest", action="store_true", help="运行内置 mock 验证")
    parser.add_argument("--registry", help="自定义注册表 JSON 路径")
    args = parser.parse_args(argv)

    resolver = GameResolver(args.registry)
    if args.selftest:
        return run_selftest(resolver)
    if args.title:
        print(json.dumps(resolver.resolve(args.title, args.summary), ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
