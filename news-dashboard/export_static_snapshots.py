"""Export the public dashboard API views as Cloudflare Pages static assets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "static"
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "index.html"
EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class SnapshotExportError(RuntimeError):
    """Raised when an existing dashboard API cannot provide a deployable view."""


class HttpResponse:
    """Small response adapter matching the Flask test client's required surface."""

    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self.body = body

    def get_json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    def get_data(self, as_text: bool = False) -> bytes | str:
        return self.body.decode("utf-8") if as_text else self.body


class HttpClient:
    """Read existing public API routes from a running Flask deployment."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def get(self, endpoint: str) -> HttpResponse:
        try:
            with urlopen(self.base_url + endpoint, timeout=30) as response:
                return HttpResponse(response.status, response.read())
        except HTTPError as error:
            return HttpResponse(error.code, error.read())
        except URLError as error:
            raise SnapshotExportError(
                f"Unable to reach source API at {self.base_url}: {error.reason}"
            ) from error


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def _request_json(client: Any, endpoint: str) -> dict[str, Any]:
    response = client.get(endpoint)
    if response.status_code != 200:
        raise SnapshotExportError(
            f"{endpoint} returned HTTP {response.status_code}: "
            f"{response.get_data(as_text=True)}"
        )
    payload = response.get_json()
    if not isinstance(payload, dict):
        raise SnapshotExportError(f"{endpoint} returned a non-object JSON response")
    return payload


def _event_ids(*payloads: dict[str, Any]) -> list[str]:
    event_ids = set()
    for payload in payloads:
        for key in ("events", "items"):
            for item in payload.get(key, []):
                if not isinstance(item, dict):
                    continue
                event_id = str(item.get("event_id") or "").strip()
                if event_id:
                    if not EVENT_ID_PATTERN.fullmatch(event_id):
                        raise SnapshotExportError(f"Unsupported event_id for static export: {event_id!r}")
                    event_ids.add(event_id)
    return sorted(event_ids)


def _static_index(template_path: Path) -> str:
    template = template_path.read_text(encoding="utf-8")
    template = template.replace(
        "{{ url_for('static', filename='style.css') }}", "style.css"
    ).replace(
        "{{ url_for('static', filename='script.js') }}", "script.js"
    )
    marker = '    <script src="script.js?v=22"></script>'
    if marker not in template:
        raise SnapshotExportError("Static entry template no longer contains the expected script tag")
    return template.replace(marker, "    <script>window.STATIC_MODE=true;</script>\n" + marker)


def export_snapshots(
    client: Any, output_dir: Path = DEFAULT_OUTPUT_DIR, template_path: Path = TEMPLATE_PATH
) -> dict[str, int]:
    """Write static equivalents of the dashboard's public, rendered API views."""
    ai_today = _request_json(client, "/api/ai/today")
    gaming_weekly = _request_json(client, "/api/gaming/weekly")
    gaming_today_new = _request_json(client, "/api/gaming/today-new")

    _write_json(output_dir / "data" / "ai_today.json", ai_today)
    _write_json(output_dir / "data" / "gaming_weekly.json", gaming_weekly)
    _write_json(output_dir / "data" / "gaming_today_new.json", gaming_today_new)

    event_ids = _event_ids(gaming_weekly, gaming_today_new)
    for event_id in event_ids:
        _write_json(
            output_dir / "data" / "gaming_events" / f"{event_id}.json",
            _request_json(client, f"/api/gaming/events/{event_id}"),
        )

    _write_text(output_dir / "index.html", _static_index(template_path))
    return {"ai_today": 1, "gaming_weekly": 1, "gaming_today_new": 1, "gaming_events": len(event_ids)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="Directory published by Cloudflare Pages (default: static)",
    )
    parser.add_argument(
        "--api-base-url",
        help="Read from an already running Flask API instead of the local application data",
    )
    args = parser.parse_args()
    if args.api_base_url:
        result = export_snapshots(HttpClient(args.api_base_url), args.output_dir)
    else:
        from app import app

        with app.test_client() as client:
            result = export_snapshots(client, args.output_dir)
    print(
        "Snapshot export complete: "
        f"ai_today={result['ai_today']}, "
        f"gaming_weekly={result['gaming_weekly']}, "
        f"gaming_today_new={result['gaming_today_new']}, "
        f"gaming_events={result['gaming_events']}"
    )


if __name__ == "__main__":
    main()
