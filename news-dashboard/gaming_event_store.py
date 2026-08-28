"""Persistent store for normalized Gaming events.

Importing and ingesting never write runtime data.  Callers persist explicitly
through :meth:`save`, whose stable default path is based on this module file.
Confirmed events are keyed by event_id; pending events use a separate
content-derived pending_key until an actual event date is confirmed.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

from gaming_attention import enrich_event
from gaming_event_normalizer import normalize_recommended_sources
from gaming_v2_rules import TIMEZONE_NAME


SHANGHAI = ZoneInfo(TIMEZONE_NAME)
STORE_SCHEMA_VERSION = 1
DEFAULT_EVENT_STORE_PATH = Path(__file__).resolve().parent / "data" / "gaming_event_store.json"


def _as_datetime(value=None) -> datetime:
    if value is None:
        return datetime.now(SHANGHAI)
    if isinstance(value, datetime):
        return value.replace(tzinfo=SHANGHAI) if value.tzinfo is None else value.astimezone(SHANGHAI)
    if isinstance(value, date):
        return datetime.combine(value, time.min, SHANGHAI)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=SHANGHAI) if parsed.tzinfo is None else parsed.astimezone(SHANGHAI)


def _iso_datetime(value=None) -> str:
    return _as_datetime(value).isoformat()


def _normalized(value) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())


def make_pending_key(event: Mapping) -> str:
    material = "|".join((
        str(event.get("game_id") or "").strip().casefold(),
        str(event.get("event_type") or "").strip(),
        _normalized(event.get("event_name")),
    ))
    return "pending-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _merge_unique(first: Iterable | None, second: Iterable | None) -> list:
    values = []
    for value in list(first or []) + list(second or []):
        if value not in (None, "") and value not in values:
            values.append(value)
    return values


def _merge_articles(first: Iterable | None, second: Iterable | None) -> list[dict]:
    merged = {}
    for article in list(first or []) + list(second or []):
        item = dict(article or {})
        key = str(item.get("id") or item.get("article_id") or item.get("url") or "").strip()
        if not key:
            key = hashlib.sha256(
                json.dumps(item, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
        merged[key] = {**merged.get(key, {}), **item}
    return list(merged.values())


def _earliest(*values) -> str:
    parsed = [_as_datetime(value) for value in values if value]
    return min(parsed).isoformat()


def _latest(*values) -> str:
    parsed = [_as_datetime(value) for value in values if value]
    return max(parsed).isoformat()


def _merge_event(existing: Mapping | None, incoming: Mapping, detected_at) -> dict:
    detected = _iso_datetime(detected_at)
    merged = dict(existing or {})
    for key, value in incoming.items():
        if key in {
            "first_detected_at", "last_detected_at", "recommended_sources",
            "key_changes", "source_article_ids", "source_articles", "pending_key",
        }:
            continue
        if value not in (None, "", []):
            merged[key] = value
        elif key not in merged:
            merged[key] = value

    merged["recommended_sources"] = normalize_recommended_sources(
        list((existing or {}).get("recommended_sources") or [])
        + list(incoming.get("recommended_sources") or [])
    )
    merged["key_changes"] = _merge_unique(
        (existing or {}).get("key_changes"), incoming.get("key_changes")
    )
    merged["source_article_ids"] = _merge_unique(
        (existing or {}).get("source_article_ids"), incoming.get("source_article_ids")
    )
    merged["source_articles"] = _merge_articles(
        (existing or {}).get("source_articles"), incoming.get("source_articles")
    )
    merged["platforms"] = _merge_unique(
        (existing or {}).get("platforms"), incoming.get("platforms")
    )
    merged["first_detected_at"] = _earliest(
        (existing or {}).get("first_detected_at"),
        incoming.get("first_detected_at"),
        detected,
    )
    merged["last_detected_at"] = _latest(
        (existing or {}).get("last_detected_at"),
        incoming.get("last_detected_at"),
        detected,
    )
    return merged


class GamingEventStore:
    def __init__(self, state: Mapping | None = None):
        self._events: dict[str, dict] = {}
        self._pending: dict[str, dict] = {}
        self.updated_at: str | None = None
        if state:
            self._load_state(state)

    def _load_state(self, state: Mapping) -> None:
        for event in state.get("events", []):
            event_id = event.get("event_id")
            if event_id:
                self._events[str(event_id)] = dict(event)
        for event in state.get("pending_events", state.get("pending", [])):
            key = event.get("pending_key") or make_pending_key(event)
            pending = dict(event)
            pending["pending_key"] = key
            pending["event_id"] = None
            self._pending[key] = pending
        self.updated_at = state.get("updated_at")

    @classmethod
    def load(cls, path=DEFAULT_EVENT_STORE_PATH) -> "GamingEventStore":
        source = Path(path)
        if not source.is_file():
            return cls()
        return cls(json.loads(source.read_text(encoding="utf-8")))

    def save(self, path=DEFAULT_EVENT_STORE_PATH) -> dict:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
        return payload

    def ingest(self, normalized, detected_at=None) -> dict:
        """Merge normalized events and return mutation counts."""
        detected = _as_datetime(detected_at)
        if isinstance(normalized, Mapping):
            confirmed = normalized.get("events", [])
            pending = normalized.get("pending", normalized.get("pending_events", []))
        else:
            confirmed = normalized or []
            pending = []

        stats = {
            "confirmed_created": 0,
            "confirmed_updated": 0,
            "pending_created": 0,
            "pending_updated": 0,
            "pending_upgraded": 0,
        }
        for event in confirmed:
            event_id = event.get("event_id")
            if not event_id:
                pending = list(pending) + [event]
                continue
            event_id = str(event_id)
            pending_key = make_pending_key(event)
            prior_pending = self._pending.pop(pending_key, None)
            incoming = dict(event)
            if prior_pending:
                incoming = _merge_event(prior_pending, incoming, detected)
                incoming.pop("pending_key", None)
                incoming["event_id"] = event_id
                stats["pending_upgraded"] += 1

            existing = self._events.get(event_id)
            self._events[event_id] = enrich_event(
                _merge_event(existing, incoming, detected), reference_time=detected
            )
            self._events[event_id]["event_id"] = event_id
            stats["confirmed_updated" if existing else "confirmed_created"] += 1

        for event in pending:
            pending_event = dict(event)
            pending_event["event_id"] = None
            pending_event["start_date"] = None
            pending_event["end_date"] = None
            key = pending_event.get("pending_key") or make_pending_key(pending_event)
            existing = self._pending.get(key)
            merged = _merge_event(existing, pending_event, detected)
            merged["pending_key"] = key
            merged["event_id"] = None
            merged["start_date"] = None
            merged["end_date"] = None
            self._pending[key] = merged
            stats["pending_updated" if existing else "pending_created"] += 1

        self.updated_at = detected.isoformat()
        return stats

    def confirmed_events(self) -> list[dict]:
        return [dict(event) for event in self._events.values()]

    def pending_events(self) -> list[dict]:
        return [dict(event) for event in self._pending.values()]

    def to_dict(self) -> dict:
        return {
            "schema_version": STORE_SCHEMA_VERSION,
            "timezone": TIMEZONE_NAME,
            "updated_at": self.updated_at,
            "events": sorted(self.confirmed_events(), key=lambda event: event["event_id"]),
            "pending_events": sorted(self.pending_events(), key=lambda event: event["pending_key"]),
        }


__all__ = ["DEFAULT_EVENT_STORE_PATH", "GamingEventStore", "make_pending_key"]
