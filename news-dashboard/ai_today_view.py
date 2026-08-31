"""Derived "Today AI Intelligence" view.

This module is deliberately read-only with respect to the pipeline output.  It
accepts the article dictionaries loaded from ``news_ai.json`` and returns
copies arranged into product-facing sections.  No taxonomy, score, rank, or
source data is changed in the input objects.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping


SHANGHAI = timezone(timedelta(hours=8))
TODAY_LIMIT = 5
RADAR_LIMIT = 5
BACKFILL_HOURS = 48
RADAR_MAX_IDLE_DAYS = 90

_CONTENT_WEIGHT = {"updates": 20.0, "trend": 12.0, "resources": -15.0}
_CATEGORY_WEIGHT = {
    "model_update": 15.0,
    "breakthrough": 15.0,
    "product_update": 12.0,
    "company": 10.0,
    "tech_direction": 8.0,
    "market_change": 8.0,
    "community_hotspot": 5.0,
}
_QUALITY_WEIGHT = {"high": 10.0, "medium": 6.0, "low": 2.0}


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _as_now(now: datetime | None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current


def _source_type(article: Mapping[str, Any]) -> str:
    return str(article.get("source_type") or article.get("source") or "").strip().lower()


def _source_name(article: Mapping[str, Any]) -> str:
    return str(article.get("source_name") or article.get("source") or "unknown").strip()


def _is_github(article: Mapping[str, Any]) -> bool:
    return _source_type(article) == "github" or str(article.get("source") or "").lower() == "github"


def _published(article: Mapping[str, Any]) -> datetime | None:
    return _parse_datetime(article.get("published") or article.get("published_at"))


def _score_number(article: Mapping[str, Any], field: str) -> float:
    try:
        return float(article.get(field) or 0)
    except (TypeError, ValueError):
        return 0.0


def _quality_score(article: Mapping[str, Any]) -> float:
    quality = str(article.get("source_quality") or "").lower()
    if quality in _QUALITY_WEIGHT:
        return _QUALITY_WEIGHT[quality]
    try:
        return min(10.0, max(0.0, float(article.get("source_priority") or 0) / 10.0))
    except (TypeError, ValueError):
        return 0.0


def _freshness_score(article: Mapping[str, Any], now: datetime) -> float:
    published = _published(article)
    if published is None:
        return 0.0
    hours = max(0.0, (now - published).total_seconds() / 3600.0)
    return max(0.0, 30.0 * (1.0 - min(hours, BACKFILL_HOURS) / BACKFILL_HOURS))


def _today_priority_score(article: Mapping[str, Any], now: datetime) -> float:
    content_type = str(article.get("content_type") or "").lower()
    category = str(article.get("category") or "").lower()
    score = _score_number(article, "value_score")
    score += _freshness_score(article, now)
    score += _CONTENT_WEIGHT.get(content_type, 0.0)
    score += _CATEGORY_WEIGHT.get(category, 0.0)
    score += _quality_score(article)
    return round(score, 3)


def _article_key(article: Mapping[str, Any]) -> str:
    return str(article.get("id") or article.get("link") or article.get("title") or "")


def _published_sort_key(article: Mapping[str, Any]) -> tuple[float, float, float, str]:
    published = _published(article)
    return (
        published.timestamp() if published else 0.0,
        _score_number(article, "importance_score"),
        _score_number(article, "value_score"),
        _article_key(article),
    )


def _priority_sort_key(article: Mapping[str, Any], now: datetime) -> tuple[float, float, str]:
    return (_today_priority_score(article, now), _freshness_score(article, now), _article_key(article))


def _clone(article: Mapping[str, Any]) -> dict[str, Any]:
    return deepcopy(dict(article))


def _non_github_by_type(articles: Iterable[Mapping[str, Any]], content_type: str) -> list[dict[str, Any]]:
    selected = [a for a in articles if not _is_github(a) and str(a.get("content_type") or "").lower() == content_type]
    return [_clone(a) for a in sorted(selected, key=_published_sort_key, reverse=True)]


def _select_today_priority(articles: list[Mapping[str, Any]], now: datetime) -> list[dict[str, Any]]:
    eligible = [a for a in articles if not _is_github(a)]
    today = now.astimezone(SHANGHAI).date()
    today_candidates = [a for a in eligible if (_published(a) and _published(a).astimezone(SHANGHAI).date() == today)]
    if len(today_candidates) < 3:
        cutoff = now - timedelta(hours=BACKFILL_HOURS)
        pool = [a for a in eligible if (_published(a) and _published(a) >= cutoff)]
    else:
        pool = today_candidates

    ranked = sorted(pool, key=lambda a: _priority_sort_key(a, now), reverse=True)
    chosen: list[dict[str, Any]] = []
    used_sources: set[str] = set()

    def take_matching(predicate, limit: int) -> None:
        for article in ranked:
            if len(chosen) >= TODAY_LIMIT or limit <= 0:
                return
            source = _source_name(article)
            if source in used_sources or not predicate(article):
                continue
            if str(article.get("content_type") or "").lower() == "resources" and sum(
                str(x.get("content_type") or "").lower() == "resources" for x in chosen
            ) >= 1:
                continue
            item = _clone(article)
            item["today_priority_score"] = _today_priority_score(article, now)
            chosen.append(item)
            used_sources.add(source)
            limit -= 1

    # Meet the requested editorial mix whenever distinct-source candidates exist.
    take_matching(lambda a: str(a.get("content_type") or "").lower() == "updates", 2)
    take_matching(lambda a: str(a.get("content_type") or "").lower() == "trend", 1)
    take_matching(lambda a: True, TODAY_LIMIT - len(chosen))
    return chosen


def _radar(articles: Iterable[Mapping[str, Any]], now: datetime) -> list[dict[str, Any]]:
    active: list[Mapping[str, Any]] = []
    for article in articles:
        if not _is_github(article) or _score_number(article, "github_score") < 50:
            continue
        metadata = article.get("metadata") or {}
        pushed = _parse_datetime(metadata.get("last_push"))
        if pushed is None or (now - pushed).days > RADAR_MAX_IDLE_DAYS:
            continue
        active.append(article)

    def key(article: Mapping[str, Any]):
        metadata = article.get("metadata") or {}
        pushed = _parse_datetime(metadata.get("last_push"))
        return (
            _score_number(article, "github_score"),
            pushed.timestamp() if pushed else 0.0,
            float(metadata.get("stars") or 0),
            float(metadata.get("forks") or 0),
            _article_key(article),
        )

    return [_clone(a) for a in sorted(active, key=key, reverse=True)[:RADAR_LIMIT]]


def build_ai_today_view(articles: Iterable[Mapping[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """Build the read-only AI Today View from existing article dictionaries."""
    current = _as_now(now)
    article_list = list(articles or [])
    return {
        "date": current.astimezone(SHANGHAI).date().isoformat(),
        "generated_at": current.astimezone(timezone.utc).isoformat(),
        "today_priority": _select_today_priority(article_list, current),
        "updates": _non_github_by_type(article_list, "updates"),
        "trends": _non_github_by_type(article_list, "trend"),
        "resources": _non_github_by_type(article_list, "resources"),
        "github_radar": _radar(article_list, current),
    }
