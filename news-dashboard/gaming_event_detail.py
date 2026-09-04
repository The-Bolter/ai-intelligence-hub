"""Read-only detail projection for a confirmed Gaming event."""

from __future__ import annotations

from datetime import date, datetime
from typing import Mapping
from zoneinfo import ZoneInfo

from gaming_attention import build_operation_signal
from gaming_v2_rules import TIMEZONE_NAME


SHANGHAI = ZoneInfo(TIMEZONE_NAME)


def _day(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(SHANGHAI).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _status(event: Mapping, today: date) -> str:
    start, end = _day(event.get("start_date")), _day(event.get("end_date"))
    if not start:
        return "unknown"
    if today < start:
        return "upcoming"
    if end and today > end:
        return "ended"
    if not end and today > start:
        return "ended"
    return "active"


def _article_sources(event: Mapping) -> list[dict]:
    seen, sources = set(), []
    for item in event.get("source_articles") or []:
        article = dict(item or {})
        url = str(article.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        role = str(article.get("source_role") or article.get("source_type") or "").lower()
        rank = 0 if role in {"official", "first_party", "first-party"} else 3 if role == "discovery" else 2 if "secondary" in role else 1
        sources.append({
            "source_name": article.get("source_name") or article.get("source_id") or "",
            "source_type": article.get("source_type") or article.get("source_role") or "",
            "url": url,
            "published_at": article.get("published_at"),
            "article_id": article.get("article_id") or article.get("stable_id") or article.get("id"),
            "_rank": rank,
        })
    sources.sort(key=lambda source: (source["_rank"], source["source_name"], source["url"]))
    for index, source in enumerate(sources[:6]):
        source["is_primary"] = index == 0
        source.pop("_rank", None)
    return sources[:6]


def _verified(event: Mapping, sources: list[dict]) -> bool:
    evidence_ids = {
        str(item.get("source_article_id") or "") for item in event.get("date_evidence") or []
        if item.get("source_article_id") and item.get("source_url") and item.get("start_date")
    }
    return any(source.get("article_id") and source.get("published_at") and str(source["article_id"]) in evidence_ids for source in sources)


def _timeline(event: Mapping, sources: list[dict]) -> list[dict]:
    nodes = []
    for source in sources:
        if _day(source.get("published_at")):
            nodes.append({"date": source["published_at"], "type": "published", "text": source.get("source_name") or "文章发布", "source_name": source.get("source_name"), "source_url": source["url"]})
    for key, kind, text in (("first_detected_at", "detected", "系统首次发现"), ("last_verified_at", "verified", "完成来源验证"), ("start_date", "event", "事件开始"), ("end_date", "event", "事件结束")):
        if _day(event.get(key)):
            nodes.append({"date": event[key], "type": kind, "text": text, "source_name": "", "source_url": ""})
    unique, result = set(), []
    for node in sorted(nodes, key=lambda item: (str(item["date"]), item["type"], item["source_url"])):
        signature = (str(node["date"]), node["type"], node["source_url"])
        if signature not in unique:
            unique.add(signature); result.append(node)
    return result[:6]


def build_event_detail(event: Mapping, reference_date: date | None = None) -> dict:
    event = dict(event)
    sources = _article_sources(event)
    return {
        "event_id": event.get("event_id"), "game_id": event.get("game_id"), "game_name": event.get("game_name"),
        "title": event.get("title") or event.get("event_name") or "", "verification_status": "verified" if _verified(event, sources) else "partial",
        "start_date": event.get("start_date"), "end_date": event.get("end_date"), "status": _status(event, reference_date or datetime.now(SHANGHAI).date()),
        "attention_score": event.get("hotspot_score", 0), "why_it_matters": event.get("why_it_matters") or event.get("operation_signal") or build_operation_signal(event) or "运营影响仍待补充。",
        "timeline": _timeline(event, sources), "sources": sources,
    }
