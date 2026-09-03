"""Small shared heartbeat for the Web process and independent scheduler."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import config

HEALTH_FILE = os.path.join(os.path.dirname(config.AI_DATA_FILE), "runtime_health.json")
HEARTBEAT_SECONDS = 90


def _mtime(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat()
    except OSError:
        return None


def write_scheduler_health(state):
    payload = {
        "state": state,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "last_ai_refresh": _mtime(config.AI_DATA_FILE),
        "last_gaming_refresh": _mtime(os.path.join(os.path.dirname(config.AI_DATA_FILE), "gaming_event_store.json")),
    }
    temporary = HEALTH_FILE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    os.replace(temporary, HEALTH_FILE)


def read_runtime_health():
    try:
        with open(HEALTH_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        heartbeat = datetime.fromisoformat(payload["heartbeat_at"])
        age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
        payload["alive"] = age <= HEARTBEAT_SECONDS
        return payload
    except (OSError, ValueError, TypeError, KeyError):
        return {"alive": False, "last_ai_refresh": None, "last_gaming_refresh": None}
