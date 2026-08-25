"""Gaming hotspot aggregation: group articles by game + event + title similarity."""

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

_BASE = os.path.dirname(os.path.abspath(__file__))
HOTSPOT_FILE = os.path.join(_BASE, "data", "game_hotspots.json")
GAMING_FILE = os.path.join(_BASE, "data", "news_gaming.json")

_STOP_WORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "with",
    "from", "by", "at", "is", "are", "be", "has", "have", "its", "it's",
    "this", "that", "as", "or", "but", "will", "can", "after", "before",
    "into", "over", "under", "about", "get", "gets", "getting", "makes",
    "making", "new", "latest", "next", "first", "final", "big", "biggest",
}

_EVENT_IMPORTANCE = {
    "Version Update": 5,
    "Release": 5,
    "Season/Event": 4,
    "Collaboration": 4,
    "Community Hotspot": 4,
    "Character/Content": 3,
    "Industry": 3,
    "General": 1,
}

_FRESH_DAYS = 7


def _load_gaming_articles():
    if not os.path.exists(GAMING_FILE):
        return []
    with open(GAMING_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("items", [])


def _title_tokens(title):
    text = (title or "").lower()
    tokens = set()
    for w in re.findall(r"[a-z][a-z0-9]{2,}", text):
        if w not in _STOP_WORDS:
            tokens.add(w)
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for i in range(len(chunk) - 1):
            tokens.add(chunk[i:i + 2])
    return tokens


def _extract_event_entity(title, summary, event_type):
    """Extract the specific event identifier (version/season/character/event name)."""
    text = ((title or "") + " " + (summary or "")).lower()
    title_text = title or ""

    # 1. Explicit version numbers
    for pat in (
        r"version\s*(?:version\s*)?([0-9]+(?:\.[0-9]+)+)",
        r"v\s*([0-9]+(?:\.[0-9]+)+)",
        r"\u7248\u672c\s*([0-9]+(?:\.[0-9]+)+)",
    ):
        m = re.search(pat, text)
        if m:
            return "Version " + m.group(1)

    # 2. Black Ops / Warzone / Battlefield numbered titles
    for pat in (
        r"(black ops|modern warfare|warzone)\s*([0-9]+)",
        r"(battlefield)\s*([0-9]+)",
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1).title() + " " + m.group(2)

    # 3. Season numbers
    for pat in (
        r"chapter\s*([0-9]+)\s*season\s*([0-9]+)",
        r"season\s*([0-9]+)",
        r"\u8d5b\u5b63\s*([0-9]+)",
    ):
        m = re.search(pat, text)
        if m:
            return "Season " + " ".join(m.groups())

    # 4. New character names
    for pat in (
        r"new character\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)",
        r"character\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)",
        r"\u65b0\u89d2\u8272\s*([\u4e00-\u9fff]{2,6})",
    ):
        m = re.search(pat, title_text + " " + (summary or ""))
        if m:
            return "Character " + m.group(1)

    # 5. Quoted event names
    quoted = re.findall(r"[\u201c\"']([^\u201d\"']{4,40})[\u201d\"']", title_text)
    if quoted:
        return quoted[0]

    # 6. Collaboration partner
    if event_type == "Collaboration":
        m = re.search(r"collab(?:oration)?\s*with\s+([A-Za-z0-9 ]+)", text)
        if m:
            return "Collab " + m.group(1).strip()[:30]

    return ""


def _similar(a_tokens, b_tokens):
    return len(a_tokens & b_tokens) >= 2


def _is_fresh(published_iso):
    try:
        dt = datetime.fromisoformat(published_iso.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
        return days <= _FRESH_DAYS
    except Exception:
        return False


def _lifecycle(articles, title, event_entity):
    """Compute event_time / countdown_days / phase."""
    now = datetime.now(timezone.utc)
    latest = None
    for a in articles:
        try:
            pt = datetime.fromisoformat(a.get("published", "").replace("Z", "+00:00"))
            if latest is None or pt > latest:
                latest = pt
        except Exception:
            pass
    event_time = latest.isoformat() if latest else now.isoformat()
    days = (latest - now).days if latest else 0

    text = (title or "").lower()
    upcoming_hint = any(k in text for k in [
        "coming", "upcoming", "release date", "launches", "launching",
        "will arrive", "arrives on", "coming soon", "starts",
    ])

    if days > 7:
        phase = "upcoming"
    elif days < -7:
        phase = "ended"
    else:
        phase = "active"
    if upcoming_hint and days >= -1:
        phase = "upcoming"

    return event_time, days, phase


def _hot_score(articles, event, has_entity):
    """Independent hotspot score - does not touch article value_score."""
    score = 0.0
    n = len(articles)
    # 1. Event importance (higher weight for operational relevance)
    score += _EVENT_IMPORTANCE.get(event, 2) * 2
    # 2. Event specificity - concrete version/season/character is more valuable
    if has_entity:
        score += 8
    # 3. Article count (reduced: accuracy over volume)
    score += min(n, 3) * 4
    # 4. Article importance (S/A/B)
    for a in articles:
        imp = a.get("importance", "D")
        if imp == "S":
            score += 6
        elif imp == "A":
            score += 4
        elif imp == "B":
            score += 2
    # 5. Freshness
    now = datetime.now(timezone.utc)
    for a in articles:
        try:
            pt = datetime.fromisoformat(a.get("published", "").replace("Z", "+00:00"))
            days = (now - pt).days
            if days <= 1:
                score += 4
            elif days <= 3:
                score += 2
        except Exception:
            pass
    # 6. Community heat
    avg_hot = sum(a.get("hotness", 0) for a in articles) / max(n, 1)
    score += avg_hot * 0.15
    # 7. Official source
    score += sum(1 for a in articles if a.get("source_weight", 0) >= 7) * 0.5
    return min(100, round(score))


_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

_EVENT_IMPACT = {
    "Version Update": "Retention",
    "Season/Event": "Retention",
    "Character/Content": "Retention",
    "Collaboration": "Acquisition",
    "Release": "Revenue",
    "Community Hotspot": "Community",
    "Industry": "Revenue",
    "General": "Community",
}


def _parse_month_date(text):
    text_l = text.lower()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text_l)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:
            pass
    m = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"\s+(\d{1,2})(?:,?\s*(\d{4}))?",
        text_l,
    )
    if m:
        month = _MONTHS[m.group(1)]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else datetime.now(timezone.utc).year
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except Exception:
            pass
    m = re.search(r"(\d{1,2})\s*[月.]\s*(\d{1,2})\s*[日号]", text_l)
    if m:
        try:
            return datetime(
                datetime.now(timezone.utc).year, int(m.group(1)), int(m.group(2)),
                tzinfo=timezone.utc,
            )
        except Exception:
            pass
    return None


def _compute_event_time(articles, title, summary):
    # Priority 1: title date
    dt = _parse_month_date(title or "")
    if dt:
        return dt.isoformat(), "title", "high"
    # Priority 2: body/summary date
    dt = _parse_month_date(summary or "")
    if dt:
        return dt.isoformat(), "body", "medium"
    # Priority 3: official announcement publish date
    official = [a for a in articles if a.get("source_weight", 0) >= 8]
    if official:
        latest = max((a.get("published", "") for a in official), default="")
        if latest:
            return latest, "official", "medium"
    # Priority 4: latest publish time fallback
    latest = max((a.get("published", "") for a in articles), default="")
    if latest:
        return latest, "publish", "low"
    return None, None, None


def _phase_for(event_start_time):
    now = datetime.now(timezone.utc)
    try:
        et = datetime.fromisoformat(event_start_time.replace("Z", "+00:00"))
        days = (et - now).days
        if days > 3:
            return "upcoming"
        if days < -7:
            return "ended"
        return "active"
    except Exception:
        return "active"


def _hot_level(event_type, event_entity, score):
    if event_type == "General":
        return "C"
    if event_type == "Community Hotspot":
        return "B"
    if event_type in ("Character/Content", "Release", "Event"):
        return "A"
    if event_type == "Version Update":
        return "S" if event_entity else "B"
    if event_type in ("Season/Event", "Collaboration", "Industry"):
        return "S" if score >= 25 else "A"
    return "C"


def build_game_hotspots():
    articles = _load_gaming_articles()
    with_entity = [a for a in articles if a.get("game_entity")]

    groups = defaultdict(list)
    for a in with_entity:
        event_entity = _extract_event_entity(
            a.get("title", ""), a.get("summary", ""), a.get("event_type", "")
        )
        groups[
            (a["game_entity"], a.get("event_type", "General"), event_entity)
        ].append(a)

    hotspots = []
    for (game, event, event_entity), group in groups.items():
        clusters = []
        for article in group:
            tokens = _title_tokens(article.get("title", ""))
            placed = False
            for cluster in clusters:
                if _similar(tokens, cluster["rep_tokens"]):
                    cluster["articles"].append(article)
                    if article.get("hotness", 0) > cluster["rep"].get("hotness", 0):
                        cluster["rep"] = article
                        cluster["rep_tokens"] = tokens
                    placed = True
                    break
            if not placed:
                clusters.append({"articles": [article], "rep": article, "rep_tokens": tokens})

        for cluster in clusters:
            cluster_articles = cluster["articles"]
            rep = cluster["rep"]
            hotspot_id = hashlib.md5(
                (str(game) + event + event_entity + rep.get("title", "")).encode("utf-8")
            ).hexdigest()[:16]
            first = min(a.get("published", "") for a in cluster_articles)
            sources = set(a.get("source", "") for a in cluster_articles)
            event_start_time, event_source, date_confidence = _compute_event_time(
                cluster_articles, rep.get("title", ""), rep.get("summary", "")
            )
            phase = _phase_for(event_start_time)
            try:
                et = datetime.fromisoformat(event_start_time.replace("Z", "+00:00"))
                countdown = (et - datetime.now(timezone.utc)).days
            except Exception:
                countdown = None
            hs = _hot_score(cluster_articles, event, bool(event_entity))
            hotspots.append({
                "hotspot_id": hotspot_id,
                "game_entity": game,
                "event_entity": event_entity,
                "event_type": event,
                "title": rep.get("title", ""),
                "articles": [
                    {"id": a["id"], "title": a.get("title", ""), "link": a.get("link", "")}
                    for a in cluster_articles
                ],
                "source_count": len(sources),
                "event_time": event_start_time,
                "event_start_time": event_start_time,
                "event_source": event_source,
                "date_confidence": date_confidence,
                "countdown_days": countdown,
                "phase": phase,
                "hot_score": hs,
                "hot_level": _hot_level(event, event_entity, hs),
                "impact_type": _EVENT_IMPACT.get(event, "Community"),
                "first_detected": first,
                "status": "active" if _is_fresh(first) else "archived",
            })

    hotspots.sort(key=lambda h: -h["hot_score"])
    _save(hotspots)
    return hotspots


def _save(hotspots):
    os.makedirs(os.path.dirname(HOTSPOT_FILE), exist_ok=True)
    with open(HOTSPOT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total": len(hotspots),
            "hotspots": hotspots,
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    result = build_game_hotspots()
    print("Hotspots:", len(result))
    for h in result[:5]:
        print(f"  [{h['game_entity']}] [{h['event_type']}] [{h['event_entity']}] score={h['hot_score']} n={len(h['articles'])} phase={h['phase']}")
        print(f"    {h['title'][:60]}")


_HOT_IMPORTANCE_SCORE = {"高": 40, "中": 25, "低": 10}
_HOT_EVENT_SCORE = {
    "version_update": 30,
    "character_release": 25,
    "activity": 20,
    "esports": 20,
}


def build_article_hotspot(
    title,
    summary=None,
    registry_path=None,
    resolver=None,
    classifier=None,
    selector=None,
):
    """Build a sortable hotspot object from title/summary text.

    Combines game resolution, event classification, and official source
    selection. Existing resolver/classifier/selector instances can be passed
    in to avoid reloading the registry. Returns {"matched": false, ...} when
    no game is recognized.
    """
    from game_resolver import GameResolver
    from event_classifier import EventClassifier
    from source_selector import SourceSelector

    resolver = resolver if resolver is not None else GameResolver(registry_path)
    classifier = classifier if classifier is not None else EventClassifier(registry_path, resolver)
    selector = selector if selector is not None else SourceSelector(registry_path)

    game = resolver.resolve(title, summary)
    if not game.get("matched"):
        return {
            "matched": False,
            "game_id": None,
            "game_name": None,
            "event_type": None,
            "importance": None,
            "hotspot_score": 0,
            "recommended_sources": [],
        }

    event = classifier.classify(title, summary, game_id=game["game_id"])
    event_type = event.get("event_type") if event.get("matched") else None
    importance = event.get("importance") if event.get("matched") else None

    hotspot_score = min(
        100,
        _HOT_IMPORTANCE_SCORE.get(importance, 0) + _HOT_EVENT_SCORE.get(event_type, 0),
    )
    recommended_sources = selector.select(game["game_id"], event_type or "").get("sources", [])

    return {
        "matched": True,
        "game_id": game["game_id"],
        "game_name": game["game_name"],
        "event_type": event_type,
        "importance": importance,
        "hotspot_score": hotspot_score,
        "recommended_sources": recommended_sources,
    }


def run_article_hotspot_selftest():
    cases = [
        (
            "版本前瞻",
            "绝区零2.8版本前瞻",
            None,
            {"matched": True, "game_id": "GMHY-ZZ", "event_type": "version_update", "importance": "高", "hotspot_score": 70},
        ),
        (
            "新角色上线",
            "原神新角色上线",
            None,
            {"matched": True, "game_id": "GMHY-YS", "event_type": "character_release", "importance": "高", "hotspot_score": 65},
        ),
        (
            "无关文本",
            "今天天气不错，适合休息",
            None,
            {"matched": False, "hotspot_score": 0, "recommended_sources": []},
        ),
    ]
    all_ok = True
    for label, title, summary, expected in cases:
        result = build_article_hotspot(title, summary)
        ok = all(result.get(key) == value for key, value in expected.items())
        if label in ("版本前瞻", "新角色上线"):
            ok = ok and bool(result.get("recommended_sources"))
        all_ok = all_ok and ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {label}: {json.dumps(result, ensure_ascii=False)}")
    return 0 if all_ok else 1
