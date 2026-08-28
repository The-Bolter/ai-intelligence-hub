"""Configuration for the Gaming Pipeline v2 weekly event calendar.

The pipeline deliberately keeps these rules separate from ``rules.py`` so the
v1 fetch/classify/score flow can remain unchanged.  Deployments may extend the
official source names/domains here without changing aggregation code.
"""

from __future__ import annotations

import re


TIMEZONE_NAME = "Asia/Shanghai"

EVENT_TYPE_LABELS = {
    "major_update": "大版本/强制更新",
    "monthly_update": "月度版本",
    "weekly_update": "周版本",
    "season_start": "赛季开启",
    "new_map": "新地图",
    "new_character": "新角色",
    "collaboration": "联动",
    "major_event": "大型活动",
    "test_or_launch": "测试/上线",
    "esports": "电竞赛事",
}

CANONICAL_EVENT_TYPES = tuple(EVENT_TYPE_LABELS)

# More specific categories must be checked before generic update/event terms.
EVENT_TYPE_KEYWORDS = {
    "weekly_update": (
        "weekly update", "weekly patch", "weekly reset", "每周更新", "周更", "周版本",
    ),
    "monthly_update": (
        "monthly update", "monthly patch", "monthly release", "月度更新", "月度版本", "月更",
    ),
    "season_start": (
        "season starts", "season start", "new season", "season begins", "赛季开启", "新赛季", "赛季更新",
    ),
    "new_map": ("new map", "map release", "新地图", "地图上线"),
    "new_character": (
        "new character", "new hero", "new agent", "character release", "新角色", "新英雄", "角色上线",
    ),
    "collaboration": ("collaboration", "collab", "crossover", "联动", "联名"),
    "test_or_launch": (
        "closed beta", "open beta", "beta test", "early access", "global launch", "official launch",
        "playtest", "公测", "内测", "删档测试", "开放测试", "正式上线", "全球上线",
    ),
    "esports": (
        "esports", "tournament", "championship", "world finals", "grand finals", "电竞", "赛事", "总决赛",
    ),
    "major_update": (
        "major update", "major patch", "expansion", "mandatory update", "大版本", "大型更新", "强制更新", "资料片",
    ),
    "major_event": (
        "major event", "anniversary event", "limited-time event", "大型活动", "周年庆", "限时活动", "主题活动",
    ),
}

# Legacy values can be consumed during the migration without changing v1.
LEGACY_EVENT_TYPE_MAP = {
    "version_update": "monthly_update",
    "character_release": "new_character",
    "activity": "major_event",
    "season_event": "season_start",
    "release": "test_or_launch",
    "Season/Event": "season_start",
    "Collaboration": "collaboration",
    "Character/Content": "new_character",
    "Release": "test_or_launch",
    "Version Update": "monthly_update",
}


def canonicalize_event_type(event_type, text=""):
    """Return one canonical Gaming v2 event type or ``None``.

    Text-specific signals take precedence over broad legacy values such as
    ``version_update`` so major, monthly, and weekly updates remain distinct.
    """
    supplied = str(event_type or "").strip()
    if supplied in EVENT_TYPE_LABELS:
        return supplied

    normalized_text = str(text or "").casefold()
    if re.search(r"\bseason\s+\d+\s+(?:starts?|begins?|launches?)\b", normalized_text):
        return "season_start"
    if re.search(r"第?\s*\d+\s*赛季(?:开启|开始|上线)", normalized_text):
        return "season_start"
    for canonical_type, keywords in EVENT_TYPE_KEYWORDS.items():
        if any(keyword.casefold() in normalized_text for keyword in keywords):
            return canonical_type

    direct = LEGACY_EVENT_TYPE_MAP.get(supplied)
    if direct:
        return direct
    supplied_folded = supplied.casefold()
    for legacy_type, canonical_type in LEGACY_EVENT_TYPE_MAP.items():
        if legacy_type.casefold() == supplied_folded:
            return canonical_type
    return None

# Explicit fields on an article take precedence.  These lists are the shared
# fallback for feeds that do not yet emit ``official``/``source_official``.
OFFICIAL_SOURCE_NAME_KEYWORDS = (
    "official", "官网", "官方", "游戏官网", "官方公告", "官方社媒",
)

OFFICIAL_SOURCE_DOMAINS = (
    "mihoyo.com", "hoyoverse.com", "playstation.com", "xbox.com",
    "nintendo.com", "steampowered.com",
)

SOURCE_TYPE_OFFICIAL = {
    "official", "official_site", "official_announcement", "official_social",
}

# Each dimension is independently capped.  Their maxima sum to exactly 100.
HEAT_FACTOR_CAPS = {
    "update_scale": 30,
    "event_importance": 20,
    "official_emphasis": 15,
    "discussion": 10,
    "game_attention": 15,
    "timing": 10,
}

UPDATE_SCALE_SCORE = {
    "major_update": 30,
    "monthly_update": 21,
    "weekly_update": 10,
    "season_start": 25,
    "new_map": 18,
    "new_character": 18,
    "collaboration": 22,
    "major_event": 20,
    "test_or_launch": 27,
    "esports": 16,
}

EVENT_IMPORTANCE_SCORE = {
    "major_update": 20,
    "monthly_update": 14,
    "weekly_update": 8,
    "season_start": 18,
    "new_map": 13,
    "new_character": 14,
    "collaboration": 17,
    "major_event": 16,
    "test_or_launch": 19,
    "esports": 15,
}

DEFAULT_GAME_ATTENTION = 8
