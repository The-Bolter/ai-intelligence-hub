"""AI Pipeline v2 classification and diversified digest composition.

The module consumes Article dictionaries after the existing v1 scoring stage.
It does not fetch data or modify the core pipeline, which keeps it suitable for
parallel development and deterministic unit tests.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import ai_v2_rules as v2_rules


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _published_timestamp(article):
    value = article.get("published_at") or article.get("published") or ""
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return 0.0


def _article_text(article):
    tags = article.get("tags") or []
    tag_labels = []
    for tag in tags:
        if isinstance(tag, dict):
            tag_labels.append(str(tag.get("l") or ""))
        else:
            tag_labels.append(str(tag))
    metadata = article.get("metadata") or {}
    topics = metadata.get("topics") or []
    return " ".join(
        [
            str(article.get("title") or ""),
            str(article.get("summary") or ""),
            " ".join(tag_labels),
            " ".join(str(topic) for topic in topics),
        ]
    ).lower()


def is_github_article(article):
    source = str(article.get("source") or "").lower()
    source_type = str(article.get("source_type") or "").lower()
    url = str(article.get("url") or article.get("link") or "").lower()
    return source == "github" or source_type == "github" or "github.com/" in url


def classify_channel(article):
    """Return one of the six stable v2 channel keys."""
    if is_github_article(article):
        return "resources"

    scores = {channel: 0 for channel in v2_rules.CHANNEL_ORDER}
    for field in ("category", "content_type"):
        prior = v2_rules.PRIOR_CHANNEL_BY_VALUE.get(
            str(article.get(field) or "").lower()
        )
        if prior:
            scores[prior] += 6

    text = _article_text(article)
    for channel, keywords in v2_rules.CHANNEL_KEYWORDS.items():
        scores[channel] += sum(1 for keyword in keywords if keyword in text)

    if max(scores.values()) <= 0:
        return "products"
    return max(
        v2_rules.CHANNEL_ORDER,
        key=lambda channel: (scores[channel], -v2_rules.CHANNEL_ORDER.index(channel)),
    )


def canonical_content_type(article, channel=None):
    channel = channel or classify_channel(article)
    if is_github_article(article):
        return "github_project"
    category = str(article.get("category") or "").lower()
    return v2_rules.CONTENT_TYPE_BY_CATEGORY.get(
        category,
        v2_rules.DEFAULT_CONTENT_TYPE[channel],
    )


def _github_home_eligible(article, policy):
    metadata = article.get("metadata") or {}
    score = _number(article.get("github_score"))
    stars = _number(metadata.get("stars"))
    return (
        score >= _number(policy["github_min_score"])
        or stars >= _number(policy["github_min_stars"])
    )


def normalize_ai_article(article, policy=None):
    """Copy an Article and add the stable fields required by the v2 contract."""
    policy = {**v2_rules.HOME_POLICY, **(policy or {})}
    normalized = copy.deepcopy(article)
    normalized["url"] = normalized.get("url") or normalized.get("link") or ""
    normalized["published_at"] = (
        normalized.get("published_at") or normalized.get("published") or ""
    )
    normalized["source_name"] = (
        normalized.get("source_name") or normalized.get("source") or "未知来源"
    )
    normalized["source_type"] = (
        normalized.get("source_type") or normalized.get("source") or "unknown"
    )
    normalized["is_github"] = is_github_article(normalized)
    normalized["channel"] = classify_channel(normalized)
    normalized["content_type"] = canonical_content_type(
        normalized, normalized["channel"]
    )

    has_minimum_content = bool(normalized.get("title") and normalized.get("url"))
    if normalized["is_github"]:
        normalized["home_eligible"] = (
            has_minimum_content and _github_home_eligible(normalized, policy)
        )
    else:
        normalized["home_eligible"] = has_minimum_content
    return normalized


def rank_articles(articles):
    """Return a stable ranking independent of the input list order."""
    return sorted(
        articles,
        key=lambda article: (
            -_number(article.get("final_score")),
            -_number(article.get("value_score")),
            -_published_timestamp(article),
            str(article.get("id") or article.get("url") or article.get("title") or ""),
        ),
    )


def compose_home_feed(articles, limit=None, policy=None):
    """Select a diversified homepage while enforcing all configured caps."""
    effective_policy = {**v2_rules.HOME_POLICY, **(policy or {})}
    limit = int(limit if limit is not None else effective_policy["limit"])
    if limit <= 0:
        return []

    candidates = rank_articles(
        [
            normalize_ai_article(article, effective_policy)
            for article in articles
        ]
    )
    candidates = [item for item in candidates if item["home_eligible"]]

    github_cap = math.floor(limit * effective_policy["github_ratio_max"])
    channel_cap = max(
        1, math.floor(limit * effective_policy["channel_ratio_max"])
    )
    source_cap = int(effective_policy["source_item_max"])

    selected = []
    selected_ids = set()
    channel_counts = Counter()
    source_counts = Counter()
    github_count = 0

    def identity(item):
        return str(item.get("id") or item.get("url") or item.get("title") or "")

    def can_select(item):
        item_id = identity(item)
        source_name = item.get("source_name") or "未知来源"
        if not item_id or item_id in selected_ids:
            return False
        if channel_counts[item["channel"]] >= channel_cap:
            return False
        if source_counts[source_name] >= source_cap:
            return False
        if item["is_github"] and github_count >= github_cap:
            return False
        return True

    def add(item):
        nonlocal github_count
        selected.append(item)
        selected_ids.add(identity(item))
        channel_counts[item["channel"]] += 1
        source_counts[item.get("source_name") or "未知来源"] += 1
        if item["is_github"]:
            github_count += 1

    # Diversity pass: reserve one slot for every available channel before fill.
    for channel in v2_rules.CHANNEL_ORDER:
        if len(selected) >= limit:
            break
        for item in candidates:
            if item["channel"] == channel and can_select(item):
                add(item)
                break

    # Ranking pass: fill remaining slots without breaking any hard cap.
    for item in candidates:
        if len(selected) >= limit:
            break
        if can_select(item):
            add(item)

    return rank_articles(selected)


def filter_by_channel(articles, channel):
    if channel not in v2_rules.CHANNEL_ORDER:
        raise ValueError(f"Unknown AI channel: {channel}")
    normalized = [normalize_ai_article(article) for article in articles]
    return rank_articles([item for item in normalized if item["channel"] == channel])


def build_ai_digest(articles, generated_at=None, limit=None, channel=None, policy=None):
    """Build the complete v2 payload used by the future Flask API."""
    effective_policy = {**v2_rules.HOME_POLICY, **(policy or {})}
    normalized = rank_articles(
        [normalize_ai_article(article, effective_policy) for article in articles]
    )
    channels = {
        key: [item for item in normalized if item["channel"] == key]
        for key in v2_rules.CHANNEL_ORDER
    }
    home_items = compose_home_feed(normalized, limit=limit, policy=effective_policy)
    selected_items = channels[channel] if channel else home_items

    channel_counts = Counter(item["channel"] for item in home_items)
    github_count = sum(1 for item in home_items if item["is_github"])
    return {
        "schema_version": 2,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "selected_channel": channel,
        "guides": copy.deepcopy(v2_rules.CHANNEL_GUIDES),
        "policy": copy.deepcopy(effective_policy),
        "stats": {
            "total_candidates": len(normalized),
            "home_count": len(home_items),
            "github_count": github_count,
            "github_ratio": round(github_count / len(home_items), 4) if home_items else 0,
            "channel_counts": {
                key: channel_counts.get(key, 0) for key in v2_rules.CHANNEL_ORDER
            },
        },
        "items": selected_items,
        "channels": channels,
    }


def write_ai_digest(articles, output_path, **kwargs):
    payload = build_ai_digest(articles, **kwargs)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _load_articles(input_path):
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    raise ValueError("Input JSON must be an article list or an object with items[]")


def main():
    parser = argparse.ArgumentParser(description="Build an AI Pipeline v2 digest")
    parser.add_argument("--input", required=True, help="Article JSON input")
    parser.add_argument("--output", required=True, help="Digest JSON output")
    parser.add_argument("--limit", type=int, default=None, help="Homepage item limit")
    args = parser.parse_args()
    write_ai_digest(_load_articles(args.input), args.output, limit=args.limit)


if __name__ == "__main__":
    main()
