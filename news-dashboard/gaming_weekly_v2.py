"""Build the Gaming v2 natural-week operations event calendar.

This module is intentionally independent from ``fetcher.py`` and ``app.py``.
The integration task can call :func:`write_game_weekly_v2` after the existing
Gaming articles have been saved, then expose the resulting JSON through its API.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from gaming_attention import enrich_event
from gaming_v2_rules import (
    DEFAULT_GAME_ATTENTION,
    EVENT_IMPORTANCE_SCORE,
    EVENT_TYPE_KEYWORDS,
    EVENT_TYPE_LABELS,
    HEAT_FACTOR_CAPS,
    LEGACY_EVENT_TYPE_MAP,
    OFFICIAL_SOURCE_DOMAINS,
    OFFICIAL_SOURCE_NAME_KEYWORDS,
    SOURCE_TYPE_OFFICIAL,
    TIMEZONE_NAME,
    UPDATE_SCALE_SCORE,
)


SHANGHAI = ZoneInfo(TIMEZONE_NAME)
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "game_weekly_v2.json"
_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9,
    "sept": 9, "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def _as_shanghai_datetime(value: datetime | date | str | None) -> datetime:
    if value is None:
        return datetime.now(SHANGHAI)
    if isinstance(value, datetime):
        return value.replace(tzinfo=SHANGHAI) if value.tzinfo is None else value.astimezone(SHANGHAI)
    if isinstance(value, date):
        return datetime.combine(value, time.min, SHANGHAI)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=SHANGHAI) if parsed.tzinfo is None else parsed.astimezone(SHANGHAI)


def natural_week(reference_time: datetime | date | str | None = None) -> tuple[date, date]:
    """Return Monday and Sunday for the Asia/Shanghai natural week."""
    current = _as_shanghai_datetime(reference_time).date()
    start = current - timedelta(days=current.weekday())
    return start, start + timedelta(days=6)


def classify_event_type(article: Mapping) -> str | None:
    """Classify an article into one stable v2 event type."""
    supplied = str(article.get("event_type") or "").strip()
    if supplied in EVENT_TYPE_LABELS:
        return supplied

    text = " ".join(str(article.get(key) or "") for key in ("title", "headline", "summary")).casefold()
    if re.search(r"\bseason\s+\d+\s+(?:starts?|begins?|launches?)\b", text):
        return "season_start"
    if re.search(r"第?\s*\d+\s*赛季(?:开启|开始|上线)", text):
        return "season_start"
    for event_type, keywords in EVENT_TYPE_KEYWORDS.items():
        if any(keyword.casefold() in text for keyword in keywords):
            return event_type
    return LEGACY_EVENT_TYPE_MAP.get(supplied)


def _valid_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _nearest_year(month: int, day: int, reference: date) -> date | None:
    candidates = [_valid_date(year, month, day) for year in (reference.year - 1, reference.year, reference.year + 1)]
    candidates = [candidate for candidate in candidates if candidate is not None]
    return min(candidates, key=lambda candidate: abs((candidate - reference).days), default=None)


def _date_from_text(text: str, reference: date) -> date | None:
    if not text:
        return None
    match = re.search(r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", text)
    if match:
        return _valid_date(*(int(value) for value in match.groups()))
    match = re.search(r"(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text)
    if match:
        year, month, day = match.groups()
        return _valid_date(int(year), int(month), int(day)) if year else _nearest_year(int(month), int(day), reference)
    match = re.search(
        r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b",
        text.casefold(),
    )
    if match:
        month, day, year = match.groups()
        return _valid_date(int(year), _MONTHS[month], int(day)) if year else _nearest_year(_MONTHS[month], int(day), reference)
    return None


def extract_event_date(article: Mapping, reference_time: datetime | date | str | None = None) -> date | None:
    """Return an explicitly confirmed event date; never fall back to publish time."""
    reference = _as_shanghai_datetime(reference_time).date()
    explicit = article.get("event_date") or article.get("event_start_date")
    if explicit:
        try:
            return date.fromisoformat(str(explicit)[:10])
        except ValueError:
            return None
    for key in ("title", "headline", "summary"):
        parsed = _date_from_text(str(article.get(key) or ""), reference)
        if parsed:
            return parsed
    return None


def _extract_version(article: Mapping) -> str:
    supplied = str(article.get("version") or article.get("season") or "").strip()
    if supplied:
        return supplied
    text = " ".join(str(article.get(key) or "") for key in ("title", "headline", "summary"))
    for pattern in (
        r"(?:version|ver\.?|v)\s*([0-9]+(?:\.[0-9]+)+)",
        r"(?:版本|更新)\s*([0-9]+(?:\.[0-9]+)+)",
        r"([0-9]+(?:\.[0-9]+)+)\s*(?:版本|版)",
        r"\bseason\s*([0-9]+)\b",
        r"第\s*([0-9]+)\s*赛季",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            prefix = "Season " if "season" in pattern or "赛季" in pattern else ""
            return prefix + match.group(1)
    return ""


def _game_name(article: Mapping) -> str:
    value = article.get("game") or article.get("game_name") or article.get("game_entity")
    if isinstance(value, Mapping):
        value = value.get("name") or value.get("game") or value.get("game_name")
    return str(value or "").strip()


def _article_url(article: Mapping) -> str:
    return str(article.get("url") or article.get("link") or "").strip()


def is_official_source(article: Mapping) -> bool:
    """Use explicit metadata first, then configurable source name/domain rules."""
    for key in ("official", "source_official", "is_official"):
        if key in article:
            return bool(article[key])
    source_type = str(article.get("source_type") or "").casefold()
    if source_type in SOURCE_TYPE_OFFICIAL:
        return True
    source_name = str(article.get("source_name") or article.get("source") or "").casefold()
    if any(keyword.casefold() in source_name for keyword in OFFICIAL_SOURCE_NAME_KEYWORDS):
        return True
    hostname = (urlparse(_article_url(article)).hostname or "").casefold()
    if any(hostname == domain or hostname.endswith("." + domain) for domain in OFFICIAL_SOURCE_DOMAINS):
        return True
    return False


def _source(article: Mapping) -> dict | None:
    url = _article_url(article)
    if not url:
        return None
    return {
        "name": str(article.get("source_name") or article.get("source") or urlparse(url).hostname or "未知来源"),
        "url": url,
        "official": is_official_source(article),
    }


def _normal(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _event_identity(article: Mapping, version: str) -> str:
    if version:
        return _normal(version)
    supplied = str(article.get("event_name") or article.get("event_entity") or "").strip()
    if supplied:
        return _normal(supplied)
    return _normal(str(article.get("headline") or article.get("title") or ""))


def _bounded_int(value, low: int, high: int) -> int:
    try:
        return max(low, min(high, round(float(value))))
    except (TypeError, ValueError):
        return low


def _timing_score(event_date: date, reference_date: date) -> int:
    distance = abs((event_date - reference_date).days)
    return max(4, 10 - distance * 2)


def _heat_factors(group: Sequence[Mapping], event_type: str, event_date: date, reference_date: date, sources: Sequence[dict]) -> dict:
    distinct_sources = len({
        (_normal(source["name"]), (urlparse(source["url"]).hostname or "").casefold())
        for source in sources
    })
    official_count = sum(1 for source in sources if source["official"])
    official_emphasis = 15 if official_count >= 2 else 12 if official_count == 1 else 0
    discussion = min(HEAT_FACTOR_CAPS["discussion"], max(0, distinct_sources - 1) * 3)
    attention_values = [article.get("game_attention") for article in group if article.get("game_attention") is not None]
    attention = max((_bounded_int(value, 0, 15) for value in attention_values), default=DEFAULT_GAME_ATTENTION)
    return {
        "update_scale": UPDATE_SCALE_SCORE[event_type],
        "event_importance": EVENT_IMPORTANCE_SCORE[event_type],
        "official_emphasis": official_emphasis,
        "discussion": discussion,
        "game_attention": attention,
        "timing": _timing_score(event_date, reference_date),
    }


def _representative(group: Sequence[Mapping]) -> Mapping:
    return max(
        group,
        key=lambda article: (
            is_official_source(article),
            _bounded_int(article.get("source_priority", article.get("source_weight", 0)), 0, 100),
            len(str(article.get("summary") or "")),
        ),
    )


def _event_id(game: str, event_date: date, event_type: str, identity: str) -> str:
    raw = "|".join((game.casefold(), event_date.isoformat(), event_type, identity))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def build_game_weekly_v2(
    articles: Iterable[Mapping],
    reference_time: datetime | date | str | None = None,
) -> dict:
    """Build a contract-compliant weekly payload without writing to disk."""
    generated_at = _as_shanghai_datetime(reference_time)
    week_start, week_end = natural_week(generated_at)
    groups: dict[tuple[str, str, str, str], list[Mapping]] = {}

    for article in articles:
        game = _game_name(article)
        event_type = classify_event_type(article)
        event_date = extract_event_date(article, generated_at)
        source = _source(article)
        if not game or not event_type or not event_date or not source:
            continue
        if not week_start <= event_date <= week_end:
            continue
        version = _extract_version(article)
        identity = _event_identity(article, version)
        key = (_normal(game), event_date.isoformat(), event_type, identity)
        groups.setdefault(key, []).append(article)

    events = []
    for (_, event_date_text, event_type, identity), group in groups.items():
        event_date = date.fromisoformat(event_date_text)
        representative = _representative(group)
        game = _game_name(representative)
        version = _extract_version(representative)
        sources_by_url = {}
        for article in group:
            source = _source(article)
            if source:
                previous = sources_by_url.get(source["url"])
                if previous is None or (source["official"] and not previous["official"]):
                    sources_by_url[source["url"]] = source
        sources = sorted(sources_by_url.values(), key=lambda source: (not source["official"], source["name"].casefold()))
        factors = _heat_factors(group, event_type, event_date, generated_at.date(), sources)
        heat_score = min(100, sum(factors.values()))
        headline = str(representative.get("headline") or representative.get("title") or "").strip()
        summary = str(representative.get("summary") or headline).strip()
        updated = max(
            (_as_shanghai_datetime(article.get("updated_at") or article.get("published_at") or article.get("published") or generated_at) for article in group),
            default=generated_at,
        )
        events.append({
            "id": _event_id(game, event_date, event_type, identity),
            "game": game,
            "event_date": event_date.isoformat(),
            "event_type": event_type,
            "version": version,
            "headline": headline,
            "summary": summary,
            "heat_score": heat_score,
            "heat_factors": factors,
            "sources": sources,
            "updated_at": updated.isoformat(),
        })

    events.sort(key=lambda event: (event["event_date"], -event["heat_score"], event["game"].casefold()))
    return {
        "schema_version": 2,
        "timezone": TIMEZONE_NAME,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "generated_at": generated_at.isoformat(),
        "events": events,
    }


def filter_events_by_type(payload_or_events: Mapping | Iterable[Mapping], event_type: str) -> list[dict]:
    """Return only events whose real primary ``event_type`` matches."""
    if event_type not in EVENT_TYPE_LABELS:
        raise ValueError(f"unsupported event_type: {event_type}")
    events = payload_or_events.get("events", []) if isinstance(payload_or_events, Mapping) else payload_or_events
    return [dict(event) for event in events if event.get("event_type") == event_type]


def write_game_weekly_v2(
    articles: Iterable[Mapping],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    reference_time: datetime | date | str | None = None,
) -> dict:
    """Build and atomically write ``game_weekly_v2.json``."""
    payload = build_game_weekly_v2(articles, reference_time=reference_time)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return payload


def compute_event_phase(event: Mapping, reference_time=None) -> str | None:
    """Compute upcoming/active/ended from actual event dates."""
    current = _as_shanghai_datetime(reference_time).date()
    try:
        start = date.fromisoformat(str(event.get("start_date") or ""))
    except ValueError:
        return None
    try:
        end = date.fromisoformat(str(event.get("end_date") or start.isoformat()))
    except ValueError:
        end = start
    if current < start:
        return "upcoming"
    if current <= end:
        return "active"
    return "ended"


def _store_collections(event_store) -> tuple[list[dict], list[dict]]:
    if hasattr(event_store, "confirmed_events") and hasattr(event_store, "pending_events"):
        return event_store.confirmed_events(), event_store.pending_events()
    if isinstance(event_store, Mapping):
        events = event_store.get("events", [])
        pending = event_store.get("pending_events", event_store.get("pending", []))
        if isinstance(events, Mapping):
            events = events.values()
        if isinstance(pending, Mapping):
            pending = pending.values()
        return [dict(event) for event in events], [dict(event) for event in pending]
    return [dict(event) for event in event_store or []], []


def _intersects_week(event: Mapping, week_start: date, week_end: date) -> bool:
    try:
        start = date.fromisoformat(str(event.get("start_date") or ""))
    except ValueError:
        return False
    try:
        end = date.fromisoformat(str(event.get("end_date") or start.isoformat()))
    except ValueError:
        end = start
    return start <= week_end and end >= week_start


def include_weekly(event: Mapping, week_start: date, week_end: date, reference_time=None) -> bool:
    """Keep the natural-week view, while retaining only live cross-week events.

    An event can carry over from a prior week solely when its explicit end date
    still overlaps this week.  Single-day and ended records are never retained
    simply to avoid an empty dashboard.
    """
    phase = compute_event_phase(event, reference_time)
    if phase == "ended":
        return False
    return _intersects_week(event, week_start, week_end)


def _score_for_sort(event: Mapping) -> float:
    try:
        return float(event.get("hotspot_score") or 0)
    except (TypeError, ValueError):
        return 0


def build_weekly_radar(event_store, reference_time=None) -> dict:
    """Derive the schema-v3 Weekly Radar from an Event Store snapshot."""
    generated_at = _as_shanghai_datetime(reference_time)
    week_start, week_end = natural_week(generated_at)
    stored_events, pending_events = _store_collections(event_store)

    events = []
    for stored in stored_events:
        if not stored.get("event_id") or not include_weekly(stored, week_start, week_end, generated_at):
            continue
        event = enrich_event(stored, reference_time=generated_at)
        event["phase"] = compute_event_phase(event, generated_at)
        events.append(event)
    events.sort(key=lambda event: (
        event.get("start_date") or "9999-12-31",
        -_score_for_sort(event),
        str(event.get("game_name") or "").casefold(),
    ))

    indexes = {"mobile": [], "pc": []}
    for event in events:
        for platform in event.get("platforms") or []:
            if platform in indexes and event["event_id"] not in indexes[platform]:
                indexes[platform].append(event["event_id"])

    return {
        "schema_version": 3,
        "view": "weekly_radar",
        "timezone": TIMEZONE_NAME,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "generated_at": generated_at.isoformat(),
        "events": events,
        "platform_indexes": indexes,
        "pending_events": pending_events,
    }


def build_today_new(event_store, reference_time=None, weekly_radar=None) -> dict:
    """Derive today's newly detected events from the current Weekly Radar."""
    generated_at = _as_shanghai_datetime(reference_time)
    today = generated_at.date()
    weekly = weekly_radar or build_weekly_radar(event_store, generated_at)
    items = []
    for event in weekly.get("events", []):
        detected = event.get("first_detected_at")
        if not detected:
            continue
        try:
            detected_at = _as_shanghai_datetime(detected)
        except (TypeError, ValueError):
            continue
        if detected_at.date() != today:
            continue
        items.append({
            "event_id": event.get("event_id"),
            "game_id": event.get("game_id"),
            "game_name": event.get("game_name"),
            "display_group": event.get("display_group"),
            "event_name": event.get("event_name"),
            "event_type": event.get("event_type"),
            "start_date": event.get("start_date"),
            "end_date": event.get("end_date"),
            "detected_at": detected_at.isoformat(),
        })
    items.sort(key=lambda item: (
        item["detected_at"],
        item.get("start_date") or "9999-12-31",
        str(item.get("game_name") or "").casefold(),
    ))
    return {
        "schema_version": 1,
        "view": "today_new",
        "timezone": TIMEZONE_NAME,
        "date": today.isoformat(),
        "week_start": weekly.get("week_start"),
        "generated_at": generated_at.isoformat(),
        "items": items,
    }


__all__ = [
    "build_today_new",
    "build_weekly_radar",
    "build_game_weekly_v2",
    "classify_event_type",
    "compute_event_phase",
    "include_weekly",
    "extract_event_date",
    "filter_events_by_type",
    "natural_week",
    "write_game_weekly_v2",
]
