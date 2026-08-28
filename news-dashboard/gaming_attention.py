"""Deterministic intelligence enrichment for canonical Gaming events."""

from __future__ import annotations

from datetime import date, datetime
from typing import Mapping
from zoneinfo import ZoneInfo

from gaming_v2_rules import TIMEZONE_NAME


SHANGHAI = ZoneInfo(TIMEZONE_NAME)

FACTOR_CAPS = {
    "event_tier": 20,
    "game_scale": 15,
    "content_volume": 15,
    "milestone_value": 20,
    "official_strength": 10,
    "operation_impact": 10,
    "timing": 10,
}

EVENT_TIER_SCORES = {
    "major_update": 20,
    "monthly_update": 14,
    "weekly_update": 7,
    "season_start": 16,
    "new_map": 13,
    "new_character": 13,
    "collaboration": 15,
    "major_event": 14,
    "test_or_launch": 18,
    "esports": 13,
}

MILESTONE_SCORES = {
    "major_update": 13,
    "monthly_update": 7,
    "weekly_update": 2,
    "season_start": 12,
    "new_map": 8,
    "new_character": 8,
    "collaboration": 11,
    "major_event": 9,
    "test_or_launch": 15,
    "esports": 9,
}

IMPACTS_BY_EVENT_TYPE = {
    "major_update": ("retention", "revenue", "content", "community"),
    "monthly_update": ("retention", "content"),
    "weekly_update": ("retention",),
    "season_start": ("retention", "revenue", "competitive"),
    "new_map": ("retention", "content", "community"),
    "new_character": ("retention", "revenue", "content"),
    "collaboration": ("acquisition", "revenue", "community"),
    "major_event": ("retention", "revenue", "community"),
    "test_or_launch": ("acquisition", "community"),
    "esports": ("community", "competitive"),
}


def attention_level(score) -> str:
    value = max(0, min(100, int(round(float(score or 0)))))
    if value >= 75:
        return "高"
    if value >= 60:
        return "中高"
    if value >= 40:
        return "中"
    return "中低"


def _reference_date(value=None) -> date:
    if value is None:
        return datetime.now(SHANGHAI).date()
    if isinstance(value, datetime):
        return (value.replace(tzinfo=SHANGHAI) if value.tzinfo is None else value.astimezone(SHANGHAI)).date()
    if isinstance(value, date):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(SHANGHAI).date()


def _date(value) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _game_scale(event: Mapping) -> int:
    explicit = event.get("game_scale_score")
    if explicit is not None:
        try:
            return max(0, min(15, round(float(explicit))))
        except (TypeError, ValueError):
            pass
    scale = str(event.get("game_scale") or "").strip().casefold()
    if scale in {"s", "a", "b", "c"}:
        return {"s": 15, "a": 12, "b": 9, "c": 6}[scale]
    try:
        return max(0, min(15, round(float(event.get("game_attention")))))
    except (TypeError, ValueError):
        return 8


def _official_strength(sources) -> int:
    official = [source for source in sources or [] if source.get("official")]
    if not official:
        return 0
    priorities = []
    for source in official:
        try:
            priorities.append(max(0, min(100, int(source.get("priority") or 0))))
        except (TypeError, ValueError):
            priorities.append(0)
    strongest = max(priorities, default=0)
    return min(10, 4 + round(strongest / 25) + min(2, len(official) - 1))


def derive_impact_types(event: Mapping) -> list[str]:
    impacts = list(IMPACTS_BY_EVENT_TYPE.get(event.get("event_type"), ("content",)))
    changes = set(event.get("key_changes") or [])
    if changes & {"新地图", "新角色", "新玩法", "新活动"} and "content" not in impacts:
        impacts.append("content")
    if changes & {"Beta测试", "公测", "联动"} and "acquisition" not in impacts:
        impacts.append("acquisition")
    return impacts


def _timing(event: Mapping, reference_time=None) -> int:
    today = _reference_date(reference_time)
    start = _date(event.get("start_date"))
    end = _date(event.get("end_date")) or start
    if not start:
        return 0
    if start <= today <= end:
        return 10
    if today < start:
        days = (start - today).days
        return 9 if days <= 3 else 7 if days <= 7 else 5 if days <= 30 else 3
    days = (today - end).days
    return 6 if days <= 3 else 3 if days <= 7 else 1


def score_event(event: Mapping, reference_time=None) -> tuple[int, dict[str, int]]:
    event_type = event.get("event_type")
    changes = list(dict.fromkeys(event.get("key_changes") or []))
    milestone = MILESTONE_SCORES.get(event_type, 4)
    if "公测" in changes:
        milestone = max(milestone, 20)
    elif "Beta测试" in changes:
        milestone = max(milestone, 18)
    impacts = derive_impact_types(event)
    factors = {
        "event_tier": EVENT_TIER_SCORES.get(event_type, 5),
        "game_scale": _game_scale(event),
        "content_volume": min(15, 3 + 3 * len(changes)),
        "milestone_value": min(20, milestone),
        "official_strength": _official_strength(event.get("recommended_sources")),
        "operation_impact": min(10, 2 + 2 * len(impacts)),
        "timing": _timing(event, reference_time),
    }
    return min(100, sum(factors.values())), factors


def build_summary(event: Mapping) -> str:
    game = str(event.get("game_name") or "该游戏").strip()
    name = str(event.get("event_name") or event.get("event_type") or "事件").strip()
    start = _date(event.get("start_date"))
    end = _date(event.get("end_date"))
    if start:
        date_text = f"{start.month}月{start.day}日"
        if end and end != start:
            date_text += f"至{end.month}月{end.day}日"
    else:
        date_text = "日期待确认"
    changes = "、".join(event.get("key_changes") or [])
    detail = f"，核心变化包括{changes}" if changes else ""
    return f"{game}{name}于{date_text}进行{detail}。"


def enrich_event(event: Mapping, reference_time=None) -> dict:
    enriched = dict(event)
    enriched["impact_types"] = derive_impact_types(enriched)
    enriched["summary"] = build_summary(enriched)
    score, factors = score_event(enriched, reference_time=reference_time)
    enriched["score_factors"] = factors
    enriched["hotspot_score"] = score
    enriched["attention_level"] = attention_level(score)
    return enriched


__all__ = [
    "FACTOR_CAPS", "attention_level", "build_summary", "derive_impact_types",
    "enrich_event", "score_event",
]
