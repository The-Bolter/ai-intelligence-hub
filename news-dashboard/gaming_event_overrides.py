"""Auditable field-level corrections for individually confirmed Gaming events."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Mapping


DEFAULT_OVERRIDE_PATH = Path(__file__).resolve().parent / "config" / "gaming_event_overrides.json"


def load_manual_event_overrides(path=DEFAULT_OVERRIDE_PATH) -> dict[str, dict]:
    """Load event-id keyed field patches without accepting complete event records."""
    source = Path(path)
    if not source.is_file():
        return {}
    payload = json.loads(source.read_text(encoding="utf-8"))
    overrides = {}
    for item in payload.get("overrides", []):
        event_id = str(item.get("event_id") or "").strip()
        fields = item.get("fields")
        if event_id and isinstance(fields, Mapping):
            overrides[event_id] = dict(fields)
    return overrides


def apply_manual_event_override(event: Mapping | None, path=DEFAULT_OVERRIDE_PATH) -> dict:
    """Return an event with its explicit confirmed fields reapplied."""
    corrected = dict(event or {})
    fields = load_manual_event_overrides(path).get(str(corrected.get("event_id") or ""))
    if fields:
        corrected.update(copy.deepcopy(fields))
    return corrected


__all__ = [
    "DEFAULT_OVERRIDE_PATH",
    "apply_manual_event_override",
    "load_manual_event_overrides",
]
