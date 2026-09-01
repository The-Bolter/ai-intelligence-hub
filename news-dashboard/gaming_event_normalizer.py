"""Deterministic Gaming event normalization for Phase 1.

The normalizer does not fetch data and never treats article publication time
as event time.  Events without an explicit date in event fields or content
remain pending with null dates and a null event_id.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from gaming_v2_rules import TIMEZONE_NAME, canonicalize_event_type


SHANGHAI = ZoneInfo(TIMEZONE_NAME)

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2,
    "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5,
    "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_RANGE_SEPARATOR = r"(?:-|–|—|~|～|至|到|to|through|until)"

_KEY_CHANGE_RULES = (
    ("新地图", (r"新地图", r"全新地图", r"\bnew\s+map\b")),
    ("新角色", (r"新角色", r"新英雄", r"全新角色", r"\bnew\s+(?:character|hero|agent)\b")),
    ("新玩法", (r"新玩法", r"全新玩法", r"\bnew\s+(?:gameplay|mode)\b")),
    ("新活动", (r"新活动", r"全新活动", r"\bnew\s+event\b")),
    ("公测", (r"公测", r"\b(?:open|public)\s+beta\b", r"\bpublic\s+test\b")),
    ("Beta测试", (r"(?<!开放)测试服", r"\b(?:closed\s+)?beta(?:\s+test)?\b")),
    ("联动", (r"联动", r"联名", r"\bcollab(?:oration)?\b", r"\bcrossover\b")),
)


def _reference_date(value=None) -> date:
    if value is None:
        return datetime.now(SHANGHAI).date()
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(SHANGHAI)
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _valid_date(year, month, day) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def _nearest_year_date(month: int, day: int, reference: date) -> date | None:
    candidates = [
        _valid_date(year, month, day)
        for year in (reference.year - 1, reference.year, reference.year + 1)
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    return min(candidates, key=lambda candidate: abs((candidate - reference).days), default=None)


def _resolve_range(
    start_year,
    start_month,
    start_day,
    end_year,
    end_month,
    end_day,
    reference: date,
) -> tuple[date | None, date | None]:
    start_month = int(start_month)
    start_day = int(start_day)
    end_month = int(end_month or start_month)
    end_day = int(end_day)

    if start_year:
        resolved_start_year = int(start_year)
    elif end_year:
        resolved_start_year = int(end_year)
    else:
        nearest = _nearest_year_date(start_month, start_day, reference)
        if nearest is None:
            return None, None
        resolved_start_year = nearest.year

    resolved_end_year = int(end_year) if end_year else resolved_start_year
    start = _valid_date(resolved_start_year, start_month, start_day)
    end = _valid_date(resolved_end_year, end_month, end_day)
    if start is None or end is None:
        return None, None

    if end < start and not end_year:
        end = _valid_date(resolved_end_year + 1, end_month, end_day)
    elif end < start and end_year and not start_year:
        start = _valid_date(resolved_start_year - 1, start_month, start_day)
    if start is None or end is None or end < start:
        return None, None
    return start, end


def _parse_explicit_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _extract_iso_dates(text: str) -> tuple[date | None, date | None] | None:
    matches = list(re.finditer(r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", text))
    if not matches:
        return None
    first = matches[0]
    start = _valid_date(*first.groups())
    if start is None:
        return None
    if len(matches) > 1:
        second = matches[1]
        between = text[first.end():second.start()]
        if re.fullmatch(rf"\s*{_RANGE_SEPARATOR}\s*", between, re.IGNORECASE):
            end = _valid_date(*second.groups())
            if end is not None and end >= start:
                return start, end
    return start, None


def _extract_day_first_dates(text: str) -> tuple[date | None, date | None] | None:
    """Parse explicit DD.MM.YYYY dates without confusing them with ISO dates."""
    matches = list(re.finditer(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)", text))
    if not matches:
        return None
    first = matches[0]
    start = _valid_date(first.group(3), first.group(2), first.group(1))
    if start is None:
        return None
    if len(matches) > 1:
        second = matches[1]
        between = text[first.end():second.start()]
        if re.fullmatch(rf"\s*{_RANGE_SEPARATOR}\s*", between, re.IGNORECASE):
            end = _valid_date(second.group(3), second.group(2), second.group(1))
            if end is not None and end >= start:
                return start, end
    return start, None


def _extract_chinese_dates(text: str, reference: date) -> tuple[date | None, date | None] | None:
    range_match = re.search(
        rf"(?:(20\d{{2}})\s*年\s*)?(\d{{1,2}})\s*月\s*(\d{{1,2}})\s*[日号]?"
        rf"\s*{_RANGE_SEPARATOR}\s*"
        rf"(?:(20\d{{2}})\s*年\s*)?(?:(\d{{1,2}})\s*月\s*)?(\d{{1,2}})\s*[日号]",
        text,
        re.IGNORECASE,
    )
    if range_match:
        return _resolve_range(*range_match.groups(), reference)

    single = re.search(r"(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text)
    if not single:
        return None
    year, month, day = single.groups()
    parsed = _valid_date(year, month, day) if year else _nearest_year_date(int(month), int(day), reference)
    return (parsed, None) if parsed else None


def _extract_english_dates(text: str, reference: date) -> tuple[date | None, date | None] | None:
    range_match = re.search(
        rf"\b({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}))?"
        rf"\s*{_RANGE_SEPARATOR}\s*"
        rf"(?:({_MONTH_PATTERN})\.?\s+)?(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}))?\b",
        text.casefold(),
        re.IGNORECASE,
    )
    if range_match:
        start_month, start_day, start_year, end_month, end_day, end_year = range_match.groups()
        return _resolve_range(
            start_year,
            _MONTHS[start_month],
            start_day,
            end_year,
            _MONTHS[end_month] if end_month else _MONTHS[start_month],
            end_day,
            reference,
        )

    single = re.search(
        rf"\b({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}))?\b",
        text.casefold(),
        re.IGNORECASE,
    )
    if not single:
        return None
    month, day, year = single.groups()
    parsed = _valid_date(year, _MONTHS[month], day) if year else _nearest_year_date(_MONTHS[month], int(day), reference)
    return (parsed, None) if parsed else None


def extract_event_dates(article: Mapping, reference_date=None) -> tuple[date | None, date | None]:
    """Extract actual event dates without consulting publication timestamps."""
    reference = _reference_date(reference_date)
    explicit_start = _parse_explicit_date(
        article.get("start_date") or article.get("event_date") or article.get("event_start_date")
    )
    explicit_end = _parse_explicit_date(article.get("end_date") or article.get("event_end_date"))
    if explicit_start is not None:
        return explicit_start, explicit_end if explicit_end and explicit_end >= explicit_start else None

    direct_text = " ".join(
        str(article.get(key) or "")
        for key in ("title", "headline", "event_name", "date_range")
    )
    body_text = " ".join(str(article.get(key) or "") for key in ("summary", "content"))
    segments = [direct_text]
    if article.get("source_is_article", True):
        segments.extend(_event_bound_date_segments(body_text))
    for extractor in (
        lambda value: _extract_iso_dates(value),
        lambda value: _extract_day_first_dates(value),
        lambda value: _extract_chinese_dates(value, reference),
        lambda value: _extract_english_dates(value, reference),
    ):
        for text in segments:
            result = extractor(text)
            if result and result[0] is not None:
                return result
    return None, None


def _event_bound_date_segments(text: str) -> list[str]:
    """Keep body dates only when they occur close to an operational signal."""
    if not text:
        return []
    date_pattern = (
        r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}\.\d{1,2}\.20\d{2}|"
        r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|"
        rf"(?:{_MONTH_PATTERN})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?"
    )
    event_pattern = (
        r"公告|新闻|版本|更新|活动|赛事|赛季|新角色|新英雄|新地图|测试|公测|上线|发布|周年|"
        r"notice|news|update|patch|event|season|hero|character|map|beta|launch|"
        r"tournament|championship"
    )
    segments = []
    for match in re.finditer(date_pattern, text, re.IGNORECASE):
        start = max(0, match.start() - 120)
        end = min(len(text), match.end() + 120)
        segment = text[start:end]
        if re.search(event_pattern, segment, re.IGNORECASE):
            segments.append(segment)
    return segments


def extract_key_changes(article: Mapping) -> list[str]:
    """Return only explicitly present, deterministic content changes."""
    changes = []
    supplied = article.get("key_changes")
    if isinstance(supplied, str):
        supplied = [supplied]
    for value in supplied or []:
        text = str(value).strip()
        if text and text not in changes:
            changes.append(text)

    # A discovery confirmation can use a platform detail page whose sidebar
    # mentions unrelated games.  Its curated, explicitly verified change list
    # is safer than mining that ambient text.
    if article.get("force_source_game_id") and changes:
        return changes

    content = " ".join(
        str(article.get(key) or "")
        for key in ("title", "headline", "summary", "content", "event_name")
    ).casefold()
    public_beta = bool(re.search(r"公测|\b(?:open|public)\s+beta\b|\bpublic\s+test\b", content))
    for label, patterns in _KEY_CHANGE_RULES:
        if label == "Beta测试" and public_beta:
            continue
        if any(re.search(pattern, content, re.IGNORECASE) for pattern in patterns) and label not in changes:
            changes.append(label)
    return changes


def _source_url_key(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, parsed.query, ""))


def _priority(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_recommended_sources(sources: Iterable[Mapping] | None) -> list[dict]:
    """Normalize SourceSelector output, preserving the strongest duplicate URL."""
    by_url = {}
    for source in sources or []:
        url = str(source.get("url") or source.get("URL") or "").strip()
        if not url:
            continue
        name = str(source.get("name") or source.get("source_name") or "").strip()
        source_type = str(source.get("source_type") or source.get("type") or "").strip()
        normalized = {
            "name": name,
            "url": url,
            "source_type": source_type,
            "official": (
                bool(source.get("official"))
                or "官方" in name
                or "官方" in source_type
                or "official" in name.casefold()
                or source_type.casefold().startswith("official")
            ),
            "priority": _priority(source.get("priority", source.get("source_priority"))),
            "fetch_method": str(source.get("fetch_method") or source.get("抓取方式") or "").strip(),
        }
        key = _source_url_key(url)
        previous = by_url.get(key)
        if previous is None or normalized["priority"] > previous["priority"]:
            by_url[key] = normalized
    return sorted(by_url.values(), key=lambda source: (-source["priority"], source["url"]))


def _extract_version(article: Mapping) -> str:
    supplied = str(article.get("version") or article.get("season") or "").strip()
    if supplied:
        return supplied
    text = " ".join(str(article.get(key) or "") for key in ("title", "headline", "summary", "content"))
    for pattern in (
        r"(?:version|ver\.?|v)\s*([0-9]+(?:\.[0-9]+)+)",
        r"(?:版本|更新)\s*([0-9]+(?:\.[0-9]+)+)",
        r"([0-9]+(?:\.[0-9]+)+)\s*(?:版本|版)",
        r"\bseason\s*([0-9]+)\b",
        r"第\s*([0-9]+)\s*赛季",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _normalize_identity(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _event_id(game_id: str, event_type: str, identity: str, start_date: date) -> str:
    material = "|".join((game_id.strip().casefold(), event_type, identity, start_date.isoformat()))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def normalize_event(
    article: Mapping,
    game: Mapping,
    classification: Mapping,
    recommended_sources: Iterable[Mapping] | None = None,
    reference_date=None,
) -> dict | None:
    """Build one canonical event, confirmed or pending."""
    text = " ".join(
        str(article.get(key) or "")
        for key in ("title", "headline", "summary", "content", "event_name")
    )
    event_type = canonicalize_event_type(
        classification.get("event_type") or article.get("event_type"), text
    )
    game_id = str(game.get("game_id") or article.get("game_id") or "").strip()
    game_name = str(game.get("game_name") or article.get("game_name") or "").strip()
    if not game_id or not game_name or event_type is None:
        return None

    event_name = str(
        article.get("event_name")
        or classification.get("event_name")
        or article.get("headline")
        or article.get("title")
        or event_type
    ).strip()
    start, end = extract_event_dates(article, reference_date=reference_date)
    version = _extract_version(article)
    identity = _normalize_identity(version or event_name)
    event_id = _event_id(game_id, event_type, identity, start) if start and identity else None

    platforms = [
        platform for platform in game.get("platforms", article.get("platforms", []))
        if platform in ("mobile", "pc")
    ]
    platforms = list(dict.fromkeys(platforms))
    display_group = str(game.get("display_group") or article.get("display_group") or "").casefold()
    if display_group not in ("mobile", "pc"):
        display_group = "mobile" if "mobile" in platforms else "pc"

    sources = recommended_sources
    if sources is None:
        sources = article.get("recommended_sources") or []
    source_article_ids = article.get("source_article_ids") or []
    if isinstance(source_article_ids, str):
        source_article_ids = [source_article_ids]
    article_id = article.get("id") or article.get("article_id")
    if article_id and article_id not in source_article_ids:
        source_article_ids = list(source_article_ids) + [article_id]
    return {
        "event_id": event_id,
        "game_id": game_id,
        "game_name": game_name,
        "platforms": platforms,
        "display_group": display_group,
        "event_type": event_type,
        "event_name": event_name,
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "key_changes": extract_key_changes(article),
        "recommended_sources": normalize_recommended_sources(sources),
        "source_article_ids": list(dict.fromkeys(source_article_ids)),
        "discovery_score": _priority(article.get("discovery_score")),
        "discovery_signals": list(dict.fromkeys(article.get("discovery_signals") or ([article.get("discovery_signal")] if article.get("discovery_signal") else []))),
        "discovery_sources": list(article.get("discovery_sources") or []),
        "verification_level": str(article.get("verification_level") or "official").strip(),
    }


__all__ = [
    "extract_event_dates",
    "extract_key_changes",
    "normalize_event",
    "normalize_recommended_sources",
]
