"""Derived "Today AI Intelligence" view.

This module is deliberately read-only with respect to the pipeline output.  It
accepts the article dictionaries loaded from ``news_ai.json`` and returns
copies arranged into product-facing sections.  No taxonomy, score, rank, or
source data is changed in the input objects.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Mapping


SHANGHAI = timezone(timedelta(hours=8))
TODAY_LIMIT = 5
RADAR_LIMIT = 5
BACKFILL_HOURS = 48
SECTION_WINDOW_HOURS = 48
SECTION_LIMITS = {"updates": (20, 40), "resources": (5, 12), "trend": (5, 15)}
SECTION_HORIZONS = {"updates": 48, "resources": 24 * 7, "trend": 24 * 7}
RADAR_MAX_IDLE_DAYS = 90
BACKFILL_PENALTY = 12.0
MAX_CATEGORY_ITEMS = 2
MAX_CONTENT_TYPE_ITEMS = 3

_COMMUNITY_SOURCE_MARKERS = ("hacker news", "reddit", "community", "论坛", "社区")
_WEAK_PRODUCT_MARKERS = (
    "free tier", "free plan", "pricing", "price change", "discount", "promotion",
    "marketing", "attract more customers", "吸引用户", "免费层", "价格变化", "营销推广",
    "小功能", "minor update", "bug fix",
)
_WEAK_COMMENTARY_MARKERS = (
    "rumor", "speculation", "speculative", "controversy", "commentary", "opinion",
    "可能", "猜测", "争议", "传闻", "据称",
)
_STRONG_MODEL_MARKERS = (
    "launch", "launched", "release", "released", "unveil", "available", "weights",
    "reasoning", "benchmark", "state-of-the-art", "发布", "上线", "正式", "模型",
)
_STRONG_PRODUCT_MARKERS = (
    "version", "v2", "2.0", "major", "launch", "launched", "introduces", "rebuild",
    "general availability", "core capability", "大版本", "核心能力", "重要功能", "上线",
)
_STRONG_TREND_MARKERS = (
    "adoption", "industrial", "industry", "market", "funding", "regulation", "benchmark",
    "产业", "工业", "行业", "市场", "融资", "监管", "格局", "路线", "采用",
)
_STRONG_HIGH_VALUE_MARKERS = _STRONG_MODEL_MARKERS + _STRONG_PRODUCT_MARKERS + _STRONG_TREND_MARKERS + (
    "study", "research", "breakthrough", "novel", "first", "sota", "研究", "突破", "首个",
)
_TECH_SIGNAL_MARKERS = (
    "new model", "model release", "model update", "weights", "reasoning", "multimodal",
    "context window", "benchmark", "inference", "api", "sdk", "rate limit", "usage limit",
    "token", "quota", "rollout", "generally available", "public access", "new capability",
    "feature launch", "agent", "agentic", "mcp", "tool use", "computer use", "browser agent",
    "coding agent", "open source", "framework", "library", "release", "technical preview",
    "architecture", "training", "模型发布", "模型升级", "开放权重", "推理能力", "多模态",
    "上下文", "调用额度", "使用限额", "价格调整", "开放使用", "新功能", "工具调用", "开源",
    "框架", "技术突破",
)

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
_GENERIC_IMPACTS = {
    "该动态为行业领域提供了新视角",
    "该动态为领域提供了新视角",
    "该动态反映了行业领域的最新发展方向，值得关注",
}
_GENERIC_IMPACT_PATTERNS = (
    r"^该动态为.+领域提供了新视角$",
    r"^该动态反映了.+领域的最新发展方向，值得关注$",
    r"^该研究可能对.+技术路线产生重要影响$",
    r"^这一商业动向反映了.+行业格局变化$",
    r"^这一趋势将影响.+行业未来发展$",
    r"^该开源项目将推动.+技术普及与生态发展$",
)
_CORE_PLACEHOLDER_MARKERS = ("点击查看原文", "查看原文", "click to read", "read more")


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
    # Future timestamps are treated as occurring now; they never receive more
    # freshness than an article published at the current instant.
    effective_published = min(published, now)
    hours = max(0.0, (now - effective_published).total_seconds() / 3600.0)
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


def _tech_signal_score(article: Mapping[str, Any]) -> float:
    """View-only hard-tech signal score; does not alter persisted scoring."""
    text = _normalized_text(article)
    hits = sum(1 for marker in _TECH_SIGNAL_MARKERS if marker in text)
    category = str(article.get("category") or "").lower()
    bonus = {"model_update": 12.0, "product_update": 10.0, "breakthrough": 12.0,
             "agent": 8.0, "model": 8.0, "tool": 6.0, "tech_direction": 6.0}.get(category, 0.0)
    return round(min(40.0, hits * 6.0 + bonus), 3)


def _priority_tier(article: Mapping[str, Any]) -> int:
    """Product priority tier used only by the Today View selector."""
    category = str(article.get("category") or "").lower()
    content_type = str(article.get("content_type") or "").lower()
    tech = _tech_signal_score(article)
    if category in {"breakthrough", "model_update"}:
        return 1
    if category == "product_update" and tech > 0:
        return 1
    if category in {"agent", "model", "tool", "app", "tech_direction"} or content_type == "resources":
        return 2
    return 3


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


def _priority_sort_key(article: Mapping[str, Any], now: datetime) -> tuple[float, float, float, str]:
    category = str(article.get("category") or "").lower()
    editorial = {"breakthrough": 5, "model_update": 4, "product_update": 3, "company": 2}.get(category, 1)
    return (_tech_signal_score(article), editorial, _today_priority_score(article, now), _article_key(article))


def _clone(article: Mapping[str, Any]) -> dict[str, Any]:
    return deepcopy(dict(article))


def _load_translation_cache() -> dict[str, dict[str, Any]]:
    """Read the existing cache without translating or persisting anything."""
    path = Path(__file__).resolve().parent / "data" / "translations.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _structured_fields(article: Mapping[str, Any], translation: Mapping[str, Any]) -> tuple[str, str]:
    raw = str(article.get("chinese_summary") or "")
    core = str(translation.get("core_info") or translation.get("summary_cn") or "").strip()
    if not core:
        core = str(article.get("core_info") or "").strip()
    impact = str(translation.get("industry_impact") or translation.get("impact") or "").strip()
    if not impact:
        impact = str(article.get("industry_impact") or "").strip()
    for segment in raw.split(" | "):
        if segment.startswith("核心信息:") and not core:
            core = segment.split(":", 1)[1].strip()
        if segment.startswith("行业影响:") and not impact:
            impact = segment.split(":", 1)[1].strip()
    if any(marker in core.lower() for marker in _CORE_PLACEHOLDER_MARKERS):
        core = ""
    if re.match(r"^\d+\s+(?:of\b|这一版)", core, flags=re.IGNORECASE):
        core = ""
    if not core:
        core = _first_summary_sentence(str(article.get("summary") or "").strip())
    if impact in _GENERIC_IMPACTS or any(re.match(pattern, impact) for pattern in _GENERIC_IMPACT_PATTERNS):
        impact = ""
    return core, impact


def _first_summary_sentence(summary: str) -> str:
    if not summary:
        return ""
    if any(marker in summary.lower() for marker in _CORE_PLACEHOLDER_MARKERS):
        return ""
    parts = re.split(r"(?<=[。！？!?])\s*|(?<=[.!?])\s+(?=[A-Z\u4e00-\u9fff])", summary)
    return next((part.strip() for part in parts if len(part.strip()) >= 12), summary[:220].strip())


def _decorate_article(article: Mapping[str, Any], translations: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    item = _clone(article)
    translation = translations.get(_article_key(article), {}) or {}
    title_cn = str(translation.get("title_cn") or "").strip()
    summary_cn = str(translation.get("summary_cn") or "").strip()
    core, impact = _structured_fields(article, translation)
    if not title_cn and any("\u4e00" <= c <= "\u9fff" for c in str(article.get("title") or "")):
        title_cn = str(article.get("title") or "")
    if not summary_cn:
        summary_cn = str(article.get("chinese_summary") or "").strip()
    item["title_cn"] = title_cn
    item["summary_cn"] = summary_cn
    item["core_info"] = core
    item["industry_impact"] = impact
    item["card_summary"] = _card_summary(article, core, impact)
    if item["card_summary"]:
        summary_cn = item["card_summary"]
    item["summary_cn"] = summary_cn
    item["translation_source"] = "cache" if translation.get("summary_cn") or translation.get("title_cn") else (
        "article.chinese_summary" if article.get("chinese_summary") else "original"
    )
    return item


def _card_summary(article: Mapping[str, Any], core: str, impact: str) -> str:
    types = article.get("summary_type") or []
    if isinstance(types, str):
        types = [types]
    label = " / ".join(str(t) for t in types if t) or "综合资讯"
    parts = [f"[{label}]"]
    if core:
        parts.append(f"核心信息: {core[:220]}")
    if impact:
        parts.append(f"行业影响: {impact[:180]}")
    return " | ".join(parts)


def _non_github_by_type(articles: Iterable[Mapping[str, Any]], content_type: str, translations: Mapping[str, Mapping[str, Any]], now: datetime) -> list[dict[str, Any]]:
    today = now.astimezone(SHANGHAI).date()
    horizon = SECTION_HORIZONS.get(content_type, SECTION_WINDOW_HOURS)
    cutoff = now - timedelta(hours=horizon)
    candidates = [
        a for a in articles
        if not _is_github(a)
        and str(a.get("content_type") or "").lower() == content_type
        and (_published(a) is not None and _published(a) >= cutoff)
    ]
    candidates.sort(key=_published_sort_key, reverse=True)
    today_items = [a for a in candidates if _published(a).astimezone(SHANGHAI).date() == today]
    min_today, maximum = SECTION_LIMITS.get(content_type, (0, 40))
    selected = today_items[:maximum]
    if len(selected) < min_today:
        for a in candidates:
            if a in selected:
                continue
            age = (now - _published(a)).total_seconds() / 3600
            min_fallback_score = 30 if content_type == "resources" else 60
            if age <= 24 or (age <= horizon and _score_number(a, "value_score") >= min_fallback_score):
                selected.append(a)
            if len(selected) >= maximum:
                break
    # Minimal Today-level event dedupe: collapse highly similar titles on the same day.
    deduped = []
    for a in selected:
        title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(a.get("title") or "").lower()).strip()
        if any(_published(a).astimezone(SHANGHAI).date() == _published(b).astimezone(SHANGHAI).date()
               and SequenceMatcher(None, title, re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(b.get("title") or "").lower()).strip()).ratio() >= 0.86
               for b in deduped):
            continue
        deduped.append(a)
    return [_decorate_article(a, translations) for a in deduped[:maximum]]


def _normalized_text(article: Mapping[str, Any]) -> str:
    return " ".join(str(article.get(field) or "") for field in ("title", "summary")).lower()


def _source_is_community(article: Mapping[str, Any]) -> bool:
    source = _source_name(article).lower()
    return any(marker in source for marker in _COMMUNITY_SOURCE_MARKERS)


def _has_marker(article: Mapping[str, Any], markers: tuple[str, ...]) -> bool:
    text = _normalized_text(article)
    return any(marker in text for marker in markers)


def _has_product_signal(article: Mapping[str, Any]) -> bool:
    if _has_marker(article, _STRONG_PRODUCT_MARKERS):
        return True
    text = _normalized_text(article)
    has_version = bool(re.search(r"\b(?:v)?\d+\.\d+(?:\.\d+)?\b", text))
    has_change = any(marker in text for marker in ("release", "released", "update", "publish", "发布", "更新", "重写"))
    return has_version and has_change


def _quality_is_sufficient(article: Mapping[str, Any]) -> bool:
    quality = str(article.get("source_quality") or "").lower()
    return quality in {"high", "medium"} or _quality_score(article) >= 6


def _today_priority_eligible(article: Mapping[str, Any]) -> bool:
    """Editorial admission gate; ordinary lists continue to expose all items."""
    if _is_github(article):
        return False
    content_type = str(article.get("content_type") or "").lower()
    category = str(article.get("category") or "").lower()
    value = _score_number(article, "value_score")
    quality_ok = _quality_is_sufficient(article)
    text = _normalized_text(article)

    if _source_is_community(article) and not (
        value >= 60 and _has_marker(article, _STRONG_HIGH_VALUE_MARKERS)
    ):
        return False

    if category == "breakthrough":
        return value >= 35 and quality_ok
    if category == "model_update":
        return value >= 45 and quality_ok and not _has_marker(article, _WEAK_COMMENTARY_MARKERS) and (
            _has_marker(article, _STRONG_MODEL_MARKERS) or value >= 60
        )
    if category == "product_update":
        return value >= 45 and quality_ok and not any(marker in text for marker in _WEAK_PRODUCT_MARKERS) and (
            _has_product_signal(article) or value >= 60
        )
    if category == "company":
        return value >= 50 and quality_ok
    if content_type == "trend":
        return value >= 30 and quality_ok and _has_marker(article, _STRONG_TREND_MARKERS)
    if content_type == "resources":
        return value >= 60 and quality_ok
    return False


def _today_priority_fallback_eligible(article: Mapping[str, Any]) -> bool:
    """Relaxed same-day admission used only after strict candidates are exhausted."""
    if _is_github(article):
        return False
    content_type = str(article.get("content_type") or "").lower()
    category = str(article.get("category") or "").lower()
    value = _score_number(article, "value_score")
    quality_ok = _quality_is_sufficient(article)
    text = _normalized_text(article)
    if _has_marker(article, _WEAK_COMMENTARY_MARKERS):
        return False
    if _source_is_community(article) and not (value >= 50 and _has_marker(article, _STRONG_HIGH_VALUE_MARKERS)):
        return False
    if category == "breakthrough":
        return value >= 28 and (quality_ok or _has_marker(article, _STRONG_HIGH_VALUE_MARKERS))
    if category == "model_update":
        return value >= 32 and _has_marker(article, _STRONG_MODEL_MARKERS)
    if category == "product_update":
        return value >= 32 and not any(marker in text for marker in _WEAK_PRODUCT_MARKERS) and _has_product_signal(article)
    if category == "company":
        return value >= 40 and quality_ok
    if content_type == "trend":
        return value >= 22 and _has_marker(article, _STRONG_TREND_MARKERS)
    if content_type == "resources":
        return value >= 50
    return False


def _take_priority_candidates(
    ranked: list[Mapping[str, Any]],
    chosen: list[dict[str, Any]],
    used_sources: set[str],
    now: datetime,
    translations: Mapping[str, Mapping[str, Any]],
    *,
    backfill: bool,
    max_items: int | None = None,
    tier: str = "strict",
) -> None:
    added = 0
    for article in ranked:
        if len(chosen) >= TODAY_LIMIT or (max_items is not None and added >= max_items):
            return
        source = _source_name(article)
        category = str(article.get("category") or "").lower()
        content_type = str(article.get("content_type") or "").lower()
        if source in used_sources:
            continue
        if sum(str(x.get("category") or "").lower() == category for x in chosen) >= MAX_CATEGORY_ITEMS:
            continue
        if sum(str(x.get("content_type") or "").lower() == content_type for x in chosen) >= MAX_CONTENT_TYPE_ITEMS:
            continue
        if content_type == "resources" and sum(str(x.get("content_type") or "").lower() == "resources" for x in chosen) >= 1:
            continue
        item = _decorate_article(article, translations)
        score = _today_priority_score(article, now)
        if backfill:
            score = round(score - BACKFILL_PENALTY, 3)
        item["today_priority_score"] = score
        item["tech_signal_score"] = _tech_signal_score(article)
        item["priority_tier"] = tier
        chosen.append(item)
        used_sources.add(source)
        added += 1


def _select_from_pool(
    pool: list[Mapping[str, Any]],
    now: datetime,
    chosen: list[dict[str, Any]],
    used_sources: set[str],
    translations: Mapping[str, Mapping[str, Any]],
    *,
    backfill: bool,
    max_items: int | None = None,
    strict: bool = True,
    tier: str = "strict",
) -> None:
    predicate = _today_priority_eligible if strict else _today_priority_fallback_eligible
    eligible = [a for a in pool if predicate(a)]
    ranked = sorted(eligible, key=lambda a: _priority_sort_key(a, now), reverse=True)
    _take_priority_candidates(
        ranked, chosen, used_sources, now, translations,
        backfill=backfill, max_items=max_items, tier=tier,
    )


def _select_today_priority(articles: list[Mapping[str, Any]], now: datetime, translations: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    eligible = [a for a in articles if not _is_github(a)]
    today = now.astimezone(SHANGHAI).date()
    today_candidates = [a for a in eligible if (_published(a) and _published(a).astimezone(SHANGHAI).date() == today)]
    chosen: list[dict[str, Any]] = []
    used_sources: set[str] = set()

    # Reserve the front of the list for hard-tech Tier 1 candidates.
    for tier_no in (1, 2, 3):
        pool = [a for a in today_candidates if _priority_tier(a) == tier_no]
        _select_from_pool(pool, now, chosen, used_sources, translations, backfill=False, tier=f"strict_tier_{tier_no}")
    if len(chosen) < 3:
        for tier_no in (1, 2, 3):
            pool = [a for a in today_candidates if _priority_tier(a) == tier_no]
            _select_from_pool(pool, now, chosen, used_sources, translations,
                              backfill=False, strict=False, max_items=3 - len(chosen), tier="fallback")
    if len(chosen) < 3:
        cutoff = now - timedelta(hours=BACKFILL_HOURS)
        fallback = [a for a in eligible if (_published(a) and cutoff <= _published(a) < now)]
        for tier_no in (1, 2, 3):
            pool = [a for a in fallback if _priority_tier(a) == tier_no]
            _select_from_pool(pool, now, chosen, used_sources, translations,
                              backfill=True, max_items=min(2, 3 - len(chosen)), tier="backfill")
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
    translations = _load_translation_cache()
    return {
        "date": current.astimezone(SHANGHAI).date().isoformat(),
        "generated_at": current.astimezone(timezone.utc).isoformat(),
        "today_priority": _select_today_priority(article_list, current, translations),
        "updates": _non_github_by_type(article_list, "updates", translations, current),
        "trends": _non_github_by_type(article_list, "trend", translations, current),
        "resources": _non_github_by_type(article_list, "resources", translations, current),
        "github_radar": [_decorate_article(a, translations) for a in _radar(article_list, current)],
    }
