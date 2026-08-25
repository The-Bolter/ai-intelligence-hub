"""
GitHub AI project data source.

Fetches popular AI/ML repositories from GitHub Search API
and converts them to the standard Article dict format
for the news-dashboard pipeline.
"""

import hashlib
import logging
import os
from datetime import datetime, timezone

import config

logger = logging.getLogger(__name__)

# ---- Config ----

GITHUB_SEARCH_QUERIES = [
    "topic:llm",
    "topic:large-language-model",
    "topic:agent+ai",
    "topic:rag",
    "topic:multimodal+ai",
    "topic:code-generation+ai",
    "ai+pushed:>2025-06+sort:stars",
]
PER_PAGE = 10
MAX_TOTAL = 30


# ---- Private helpers ----

def _hash_entry(title, link):
    return hashlib.md5(((title or "") + (link or "")).encode("utf-8")).hexdigest()


def _stars_to_weight(stars):
    if stars >= 50000:
        return 9
    if stars >= 10000:
        return 8
    if stars >= 5000:
        return 7
    if stars >= 1000:
        return 6
    if stars >= 100:
        return 5
    return 4


def _github_hotness(repo):
    stars = repo.get("stargazers_count", 0)
    pushed = repo.get("pushed_at", "")
    if pushed:
        dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
    else:
        days = 999
    freshness = 1.0 if days < 30 else (0.5 if days < 90 else 0.1)
    score = (stars ** 0.5) * 0.5 + freshness * 20
    return min(100, round(score))


def _time_ago(dt):
    s = (datetime.now(timezone.utc) - dt).total_seconds()
    if s < 60:
        return "刚刚"
    m = int(s // 60)
    if m < 60:
        return f"{m} 分钟前"
    h = int(m // 60)
    if h < 24:
        return f"{h} 小时前"
    return f"{int(h // 24)} 天前"


def _make_tags(repo):
    tags = []
    for t in (repo.get("topics") or []):
        tags.append({"t": "tech", "l": t})
    lang = repo.get("language")
    if lang:
        tags.append({"t": "lang", "l": lang})
    return tags


# ---- Public API ----

def fetch_github_projects():
    """Fetch AI-related GitHub repos and return as Article dict list."""
    import requests

    items = []
    seen = set()

    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for query in GITHUB_SEARCH_QUERIES:
        if len(items) >= MAX_TOTAL:
            break

        url = "https://api.github.com/search/repositories"
        params = {"q": query, "sort": "stars", "order": "desc", "per_page": PER_PAGE}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code == 403:
                logger.warning("GitHub API rate limited, stopping queries")
                break
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("GitHub query '%s' failed: %s", query[:30], exc)
            continue

        for repo in data.get("items", []):
            full_name = repo.get("full_name", "")
            if not full_name or full_name in seen:
                continue
            seen.add(full_name)

            title = full_name
            desc = (repo.get("description") or "")[:200]
            link = repo.get("html_url", "")
            created = repo.get("created_at", "2024-01-01T00:00:00Z")
            pt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            tags = _make_tags(repo)

            item = {
                "id": _hash_entry(title, link),
                "title": f"{title} — {desc[:60]}" if desc else title,
                "link": link,
                "summary": desc,
                "source": "github",
                "source_name": config.GITHUB_SOURCE["source_name"],
                "source_type": config.GITHUB_SOURCE["source_type"],
                "source_region": config.GITHUB_SOURCE["source_region"],
                "source_priority": config.GITHUB_SOURCE["source_priority"],
                "source_weight": _stars_to_weight(repo.get("stargazers_count", 0)),
                "published": pt.isoformat(),
                "published_ago": _time_ago(pt),
                "tags": tags,
                "summary_type": "auto",
                "hotness": _github_hotness(repo),
                "source_quality": "high",
                "metadata": {
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "language": repo.get("language"),
                    "topics": repo.get("topics", []),
                    "last_push": repo.get("pushed_at", ""),
                    "license": (repo.get("license") or {}).get("spdx_id"),
                    "open_issues": repo.get("open_issues_count", 0),
                },
            }
            items.append(item)
            if len(items) >= MAX_TOTAL:
                break

    logger.info("GitHub: fetched %d projects", len(items))
    return items
