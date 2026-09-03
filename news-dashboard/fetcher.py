# news-dashboard/fetcher.py

import os
import json
import hashlib
import logging
import tempfile
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone
from html import unescape as html_unescape

import feedparser
import requests
from bs4 import BeautifulSoup

import config
import rules
from translation_service import try_translate_article, get_cached_translation

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
_AI_SOURCE_FAILURES = {}
_AI_SOURCE_COUNTS = {}

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
})


# ---------- Utility ----------

def _hash_entry(title, link):
    return hashlib.md5(((title or "") + (link or "")).encode("utf-8")).hexdigest()


def _clean_html(raw):
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    return html_unescape(soup.get_text(separator=" ", strip=True))[:300]


def _parse_published(entry):
    for field in ("published_parsed", "updated_parsed"):
        tp = getattr(entry, field, None)
        if tp and len(tp) >= 6:
            try:
                return datetime(*tp[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return datetime.now(timezone.utc)


def _freshness(pub_time):
    hrs = max(0, (datetime.now(timezone.utc) - pub_time).total_seconds() / 3600)
    if hrs > config.FRESHNESS_MAX_HOURS:
        return 0.0
    return 2 ** (-hrs / config.FRESHNESS_HALF_LIFE)


def _kw_bonus(title, keywords):
    if not title:
        return 0.0
    lower = title.lower()
    hits = sum(1 for kw in keywords if kw.lower() in lower)
    return min(hits * 0.15, 0.6)


def _hotness(entry, feed, cat):
    fresh = _freshness(_parse_published(entry))
    sw = feed["weight"] / 10.0
    kws = config.AI_HOT_KEYWORDS if cat == "ai" else config.GAMING_HOT_KEYWORDS
    kwb = _kw_bonus(entry.get("title"), kws)
    L = len(entry.get("title", ""))
    lb = 0.1 if 15 <= L <= 80 else 0.0
    return round(min(fresh * 40 + sw * 30 + kwb * 20 + lb * 10, 100), 1)


# ---------- Tags ----------

def _extract_tags(title, summary, cat):
    text = ((title or "") + " " + (summary or "")).lower()
    tags = []
    if cat == "ai":
        for kw, lb in config.AI_TECH_TAGS.items():
            if kw in text:
                tags.append({"t": "tech", "l": lb})
        for kw, lb in config.AI_COMPANY_TAGS.items():
            if kw in text:
                tags.append({"t": "company", "l": lb})
        for kw, lb in config.AI_SOLUTION_TAGS.items():
            if kw in text:
                tags.append({"t": "solution", "l": lb})
        for kw, lb in config.AI_ZH_TECH_TAGS.items():
            if kw in text:
                tags.append({"t": "tech", "l": lb})
        for kw, lb in config.AI_ZH_COMPANY_TAGS.items():
            if kw in text:
                tags.append({"t": "company", "l": lb})
    else:
        for kw, lb in config.GAMING_TECH_TAGS.items():
            if kw in text:
                tags.append({"t": "tech", "l": lb})
        for kw, lb in config.GAMING_COMPANY_TAGS.items():
            if kw in text:
                tags.append({"t": "company", "l": lb})
        for kw, lb in config.GAMING_ZH_TECH_TAGS.items():
            if kw in text:
                tags.append({"t": "tech", "l": lb})
        for kw, lb in config.GAMING_ZH_COMPANY_TAGS.items():
            if kw in text:
                tags.append({"t": "company", "l": lb})
    seen = set()
    out = []
    for t in tags:
        if t["l"] not in seen:
            seen.add(t["l"])
            out.append(t)
    return out[:6]


_TYPE_MAP = [
    (["paper", "arxiv", "research", "study", "survey", "benchmark"], "研究进展"),
    (["release", "launch", "announce", "introduc", "beta", "preview"], "产品动态"),
    (["funding", "acquisition", "partner", "invest", "revenue"], "商业动态"),
    (["regulation", "policy", "law", "ban", "trend", "report"], "行业趋势"),
    (["open source", "github", "hugging face", "repository"], "开源项目"),
    (["guide", "tutorial", "how to", "introduction"], "技术教程"),
]


def _summary_type(title, summary):
    text = ((title or "") + " " + (summary or "")).lower()
    types = [lb for kws, lb in _TYPE_MAP if any(k in text for k in kws)]
    # Also check Chinese type keywords
    try:
        zh_types = [lb for kws, lb in config.ZH_TYPE_MAP if any(k in text for k in kws)]
        types.extend(zh_types)
    except AttributeError:
        pass
    return types if types else ["综合资讯"]


def _chinese_summary(title, summary, tags, types_):
    """Generate structured Chinese summary in industry analyst format."""
    parts = []
    type_str = " / ".join(types_) if types_ else "综合资讯"
    parts.append("[" + type_str + "]")

    # Key entities
    te = [t["l"] for t in tags if t["t"] == "tech"]
    co = [t["l"] for t in tags if t["t"] == "company"]

    # Build entity context
    ctx = []
    if co:
        ctx.append(" / ".join(co[:3]))
    if te:
        ctx.append(" / ".join(te[:3]))
    if ctx:
        parts.append(" ".join(ctx))

    # One-sentence summary
    key_sentence = ""
    if summary:
        sents = [s.strip() for s in summary.replace("...",".").replace("?",".").split(".") if len(s.strip()) > 15]
        if sents:
            key_sentence = sents[0][:150]
        else:
            key_sentence = summary[:150]
    if key_sentence:
        parts.append(key_sentence)

    # Core info (3-5 key points)
    if summary and len(summary) > 40:
        sents = [s.strip() for s in summary.replace("...",".").replace("?",".").split(".") if len(s.strip()) > 20]
        action_kws = ['releas', 'launch', 'announc', 'introduc', 'found', 'creat', 'develop', 'build', 'show', 'demonstrat', 'publish', 'updat', 'new', 'first', 'present']
        core_items = []
        for s in sents:
            is_key = any(kw in s.lower() for kw in action_kws)
            if is_key or (len(s) > 40 and len(core_items) < 3):
                core_items.append(s[:120])
                if len(core_items) >= 3:
                    break
        if not core_items and sents:
            core_items = [s[:120] for s in sents[:3]]
        if core_items:
            deduped = []
            for item in core_items:
                if key_sentence and key_sentence[:40] in item:
                    continue
                deduped.append(item)
            if not deduped:
                deduped = core_items[:1]
            core_text = "; ".join(deduped)
            parts.append("核心信息: " + core_text)

    # Industry impact
    domain_parts = []
    if te:
        domain_parts.extend(te[:3])
    if co:
        domain_parts.extend(co[:2])
    domain = "/".join(domain_parts) if domain_parts else "行业"

    first_type = types_[0] if types_ else ''
    impact = ''
    for t_type, t_text in [('产品动态', '该动态反映了{}领域的最新发展方向，值得关注'), ('研究进展', '该研究可能对{}技术路线产生重要影响'), ('商业动态', '这一商业动向反映了{}行业格局变化'), ('行业趋势', '这一趋势将影响{}行业未来发展'), ('开源项目', '该开源项目将推动{}技术普及与生态发展')]:
        if t_type in first_type:
            impact = t_text.format(domain)
            break
    # Do not invent a generic impact for unclassified/general articles.
    # A blank impact is preferable to repeating an unsupported conclusion.
    if impact:
        parts.append("行业影响: " + impact)

    return " | ".join(parts)
def _fetch(feed):
    try:
        r = _session.get(feed["url"], timeout=15)
        r.raise_for_status()
        entries = feedparser.parse(r.content).entries
        # Official feeds occasionally expose an archive or duplicate URLs.
        # Apply an opt-in bounded window only to feeds that request it.
        limit = feed.get("max_entries")
        if not limit:
            return entries
        seen = set()
        clean = []
        for entry in entries:
            link = str(entry.get("link") or entry.get("id") or "").strip()
            if link:
                parts = urlsplit(link)
                key = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
            else:
                key = str(entry.get("title") or "").strip().lower()
            if key in seen:
                continue
            seen.add(key)
            clean.append(entry)
            if len(clean) >= int(limit):
                break
        return clean
    except Exception as e:
        logger.warning("Fetch failed: %s - %s", feed["name"], e)
        return []


def _to_dict(entry, feed, cat):
    pt = _parse_published(entry)
    title = _clean_html(entry.get("title", "")).strip()
    raw = _clean_html(entry.get("summary", entry.get("description", "")))
    summary = raw[:200]
    tags = _extract_tags(title, summary, cat)
    st = _summary_type(title, summary)
    return {
        "id": _hash_entry(title, entry.get("link", "")),
        "title": title or "(No title)",
        "link": entry.get("link", ""),
        "summary": summary,
        "content_type": "news" if cat != "ai" else "",
        "source": feed["name"],
        "source_name": feed.get("source_name", feed["name"]),
        "source_type": feed.get("source_type", "rss"),
        "source_region": feed.get("source_region", "CN" if feed.get("lang") == "zh" else "Global"),
        "source_priority": feed.get("source_priority", feed.get("weight", 6)),
        "source_weight": feed["weight"],
        "published": pt.isoformat(),
        "published_ago": _time_ago(pt),
        "category": cat,
        "tags": tags,
        "summary_type": st,
        "chinese_summary": _chinese_summary(title, summary, tags, st),
    }


def _time_ago(pt):
    s = (datetime.now(timezone.utc) - pt).total_seconds()
    if s < 60:
        return "刚刚"
    m = int(s // 60)
    if m < 60:
        return f"{m} 分钟前"
    h = int(m // 60)
    if h < 24:
        return f"{h} 小时前"
    return f"{int(h // 24)} 天前"



# ---------- Relevance Filter ----------

def _is_relevant(item, cat):
    text = ((item.get("title") or "") + " " + (item.get("summary") or "")).lower()
    if cat == "ai":
        extra = ["ai", "artificial intelligence", "neural", "model",
                 "llm", "language model", "training", "inference", "chatbot",
                 "chatgpt", "algorithm", "compute", "data"]
        kws = config.AI_HOT_KEYWORDS + extra
    else:
        extra = ["game", "gaming", "play", "studio", "developer"]
        kws = config.GAMING_HOT_KEYWORDS + extra
    for kw in kws:
        if kw.lower() in text:
            return True
    return False

# ---------- Classification & Value Score ----------

def _keyword_hits(text, keywords):
    return sum(1 for kw in keywords if kw and kw.lower() in text)


def _is_project_source(article):
    source_type = str(article.get("source_type") or "").lower()
    source = str(article.get("source") or "").lower()
    if source_type == "github" or source == "github":
        return True
    text = ((article.get("title") or "") + " " + (article.get("summary") or "")).lower()
    for marker in ("github", "hugging face", "huggingface", "开源项目", "open-source project"):
        if marker in text:
            return True
    return False


_RESOURCE_TOOL_MARKERS = (
    "mcp", "model context protocol", "skill", "plugin", "extension",
    "插件", "扩展",
)


def _classify_resource_category(article):
    topics = [str(t).lower() for t in ((article.get("metadata") or {}).get("topics") or [])]
    title_lower = (article.get("title") or "").lower()
    summary_lower = (article.get("summary") or "").lower()
    combined = " ".join(topics) + " " + title_lower + " " + summary_lower

    # Tool-domain markers take precedence over overlapping agent keywords.
    if any(marker in combined for marker in _RESOURCE_TOOL_MARKERS):
        return "tool"

    scores = {}
    for cat, kws in rules.AI_TAXONOMY["resources"].items():
        score = 0
        for kw in kws:
            k = kw.lower()
            if k and any(k in t for t in topics):
                score += 3
            if k and k in title_lower:
                score += 2
            if k and k in summary_lower:
                score += 1
        scores[cat] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "tool"


def _classify_ai_intel(article):
    """Classify an AI article into (content_type, category) from AI_TAXONOMY."""
    if _is_project_source(article):
        return "resources", _classify_resource_category(article)

    text = ((article.get("title") or "") + " " + (article.get("summary") or "")).lower()

    trend_scores = {
        cat: _keyword_hits(text, kws)
        for cat, kws in rules.AI_TAXONOMY["trend"].items()
    }
    if max(trend_scores.values()) > 0:
        return "trend", max(trend_scores, key=trend_scores.get)

    update_scores = {
        cat: _keyword_hits(text, kws)
        for cat, kws in rules.AI_TAXONOMY["updates"].items()
    }
    best = max(update_scores, key=update_scores.get)
    if update_scores[best] <= 0:
        best = "product_update"
    return "updates", best

def _classify_applications(title, summary):
    text = ((title or "") + " " + (summary or "")).lower()
    apps = []
    for a, kws in rules.AI_APPLICATION_KEYWORDS.items():
        for kw in kws:
            if kw and kw.lower() in text:
                apps.append(a)
                break
    return apps

def _extract_game_entity(title, summary):
    text = ((title or "") + " " + (summary or "")).lower()
    for market, cfg in rules.GAME_ENTITIES.items():
        for game, kws in cfg["games"].items():
            for kw in kws:
                if kw and kw.lower() in text:
                    return game, cfg["region"], cfg["type"]
    return "", "", ""


def _extract_event_type(title, summary):
    text = ((title or "") + " " + (summary or "")).lower()
    for event, kws in rules.GAME_EVENT_TYPE_KEYWORDS.items():
        for kw in kws:
            if kw and kw.lower() in text:
                return event
    return "General"


def _classify_gaming_category(title, summary):
    text = ((title or "") + " " + (summary or "")).lower()
    scores = {}
    for cat, groups in rules.GAMING_CATEGORY_SCORING.items():
        score = 0
        for group_key, group_cfg in groups.items():
            for kw in group_cfg["keywords"]:
                if kw.lower() in text:
                    score += group_cfg["weight"]
        scores[cat] = score
    best = max(scores, key=scores.get)
    if scores[best] < 2:
        return "Other"
    return best

def _compute_value_score(item, cat):
    text = ((item.get("title") or "") + " " + (item.get("summary") or "")).lower()

    # 1. Category base score
    category = item.get("category", "Other")
    if cat == "ai":
        base_scores = rules.AI_CATEGORY_BASE_SCORE
    else:
        base_scores = rules.GAMING_CATEGORY_BASE_SCORE
    base_score = base_scores.get(category, 0)

    # 2. Content dimension score (practicality + efficiency + trend)
    dims = rules.AI_SCORE_DIMENSIONS if cat == "ai" else rules.GAMING_SCORE_DIMENSIONS
    dim_total = 0.0
    for dim_name, dim_cfg in dims.items():
        score = 0
        for kw, pts in dim_cfg["keywords"].items():
            if kw.lower() in text:
                score += pts
        score = min(score, dim_cfg["max"])
        dim_total += score * dim_cfg["weight"]

    # 3. Source weight bonus
    sw = item.get("source_weight", 0)
    if sw >= 8:
        bonus = 5
    elif sw >= 7:
        bonus = 3
    elif sw >= 6:
        bonus = 1
    else:
        bonus = 0

    # Final: cap 0-100, use round() instead of int()
    final = base_score + dim_total + bonus
    final = max(0, min(100, final))
    return round(final)

def _github_value_bonus(item):
    meta = item.get("metadata", {}) or {}
    stars = meta.get("stars", 0)
    forks = meta.get("forks", 0)
    bonus = 0
    if stars >= 100000: bonus += 10
    elif stars >= 50000: bonus += 8
    elif stars >= 10000: bonus += 5
    if forks >= 1000: bonus += 2
    return min(bonus, 15)


def _github_score(item):
    """Repo-specific 0-100 score: stars + forks + topics + activity."""
    meta = item.get("metadata") or {}
    stars = meta.get("stars", 0) or 0
    forks = meta.get("forks", 0) or 0
    topics = meta.get("topics") or []
    pushed = meta.get("last_push", "")

    star_score = 2
    for threshold, score in rules.GITHUB_STARS_SCORES:
        if stars >= threshold:
            star_score = score
            break

    fork_score = 1
    for threshold, score in rules.GITHUB_FORKS_SCORES:
        if forks >= threshold:
            fork_score = score
            break

    topic_score = min(
        rules.GITHUB_TOPIC_SCORE_MAX,
        len(topics) * rules.GITHUB_TOPIC_SCORE_PER,
    )

    activity_score = 0
    if pushed:
        try:
            dt = datetime.fromisoformat(str(pushed).replace("Z", "+00:00"))
            days = max(0, (datetime.now(timezone.utc) - dt).days)
            for max_days, score in rules.GITHUB_ACTIVITY_SCORES:
                if days < max_days:
                    activity_score = score
                    break
        except Exception:
            activity_score = 0

    return min(100, star_score + fork_score + topic_score + activity_score)


def _get_importance(value_score, cat):
    thresholds = rules.IMPORTANCE_AI if cat == "ai" else rules.IMPORTANCE_GAMING
    for level, threshold in thresholds:
        if value_score >= threshold:
            return level
    return "D"


def _compute_final_score(item):
    """final_score = value component + source_priority + time-decayed hotness.

    GitHub projects rank by github_score so stars/forks bonus cannot inflate
    their position relative to news.
    """
    if item.get("source") == "github":
        value = float(item.get("github_score") or 0)
    else:
        value = float(item.get("value_score") or 0)
    priority = float(item.get("source_priority") or 0)
    hotness = float(item.get("hotness") or 0)
    return round(value + priority + hotness)

def _extract_entities(title, summary, tags):
    entities = []
    for t in tags:
        if t["t"] in ("company", "tech"):
            entities.append(t["l"])
    return entities[:6]

def _compute_source_quality(feed, cat):
    name = feed.get("name", "")
    if cat == "ai":
        return rules.AI_SOURCE_QUALITY.get(name, "low")
    return rules.GAMING_SOURCE_QUALITY.get(name, "low")




_GAMING_TRANSLATE_EVENTS = ("Version Update", "Season/Event", "Collaboration", "Release")


def _should_translate_article(article, cat, min_score):
    if cat == "gaming":
        if article.get("game_entity") and article.get("event_type") in _GAMING_TRANSLATE_EVENTS:
            return True
        return False
    policy = rules.TRANSLATION_POLICY
    if article.get("importance") in policy.get("importance_levels", ("S", "A")):
        return True
    if article.get("value_score", 0) >= policy.get("min_value_score", 60):
        return True
    if article.get("source_priority", 0) >= policy.get("min_source_priority", 8):
        return True
    return False


def _run_auto_translate(articles, cat):
    policy = rules.TRANSLATION_POLICY
    if not policy.get("enable_auto_translate", False):
        return
    min_score = policy.get("min_value_score", 60)
    max_per_refresh = 10
    eligible = 0
    num_t = 0
    num_s = 0
    for article in articles:
        if num_t + num_s >= max_per_refresh:
            break
        if not _should_translate_article(article, cat, min_score):
            continue
        if get_cached_translation(article["id"]):
            eligible += 1
            continue
        eligible += 1
        r = _maybe_translate_article(article)
        if r and r.get("status") == "translated":
            num_t += 1
        else:
            num_s += 1
    if eligible > 0:
        logger.info("[%s] Auto-translate: %d eligible, %d translated, %d skipped, %d cached (max %d)",
                    cat, eligible, num_t, num_s, eligible - num_t - num_s, max_per_refresh)


def _maybe_translate_article(article):
    return try_translate_article(
        article_id=article["id"],
        title=article.get("title", ""),
        summary=article.get("summary", ""),
    )

def fetch_category(cat):
    feeds = config.AI_FEEDS if cat == "ai" else config.GAMING_FEEDS
    feeds = [feed for feed in feeds if feed.get("status") != "disabled"]
    items = []
    failures = {}
    counts = {}
    for feed in feeds:
        name = feed.get("source_name", feed.get("name", "unknown"))
        try:
            entries = _fetch(feed)
            counts[name] = len(entries)
            for e in entries:
                d = _to_dict(e, feed, cat)
                d["hotness"] = _hotness(e, feed, cat)
                d["source_quality"] = _compute_source_quality(feed, cat)
                items.append(d)
        except Exception as exc:
            failures[name] = f"{type(exc).__name__}: {exc}"
            logger.warning("Source isolated: %s - %s", name, failures[name])
    # ---- GitHub AI projects ----
    if cat == "ai":
        from github_fetcher import fetch_github_projects
        for gh in fetch_github_projects():
            items.append(gh)

    seen = {}
    for i in items:
        eid = i["id"]
        if eid not in seen or i["hotness"] > seen[eid]["hotness"]:
            seen[eid] = i
    result = sorted(seen.values(), key=lambda x: x["hotness"], reverse=True)
    # Guard the final AI collection as well: a provider can return an archive
    # through multiple feed pages, so per-feed limits alone are insufficient.
    if cat == "ai":
        bounded = []
        counts = {}
        for item in result:
            name = item.get("source_name") or item.get("source") or ""
            limit = next((int(f.get("max_entries")) for f in config.AI_FEEDS
                          if f.get("source_name") == name and f.get("max_entries")), None)
            if limit is not None:
                counts[name] = counts.get(name, 0)
                if counts[name] >= limit:
                    continue
                counts[name] += 1
            bounded.append(item)
        result = bounded

    # Merge AI status from ai_insights.json (no auto-pending)
    insight_map = _get_insight_map()
    for i in result:
        _merge_ai_fields(i, insight_map)
        # Classification and value scoring
        i["domain"] = cat
        if cat == "ai":
            i["content_type"], i["category"] = _classify_ai_intel(i)
            i["application"] = _classify_applications(i.get("title",""), i.get("summary",""))
        else:
            i["category"] = _classify_gaming_category(i.get("title",""), i.get("summary",""))
            i["technology_type"] = []
            i["application"] = []
            i["game_entity"], i["game_region"], i["game_type"] = _extract_game_entity(i.get("title",""), i.get("summary",""))
            i["event_type"] = _extract_event_type(i.get("title",""), i.get("summary",""))
        i["entity"] = _extract_entities(i.get("title",""), i.get("summary",""), i.get("tags",[]))
        i["value_score"] = _compute_value_score(i, cat)
        if i.get("source") == "github":
            i["value_score"] = min(100, i["value_score"] + _github_value_bonus(i))
        if i.get("source") == "github":
            i["github_score"] = _github_score(i)
        i["importance"] = _get_importance(i["value_score"], cat)
        if cat == "ai":
            i["final_score"] = _compute_final_score(i)

    if cat == "ai":
        result.sort(
            key=lambda x: (x.get("final_score", 0), x.get("value_score", 0), x.get("hotness", 0)),
            reverse=True,
        )
    for n, i in enumerate(result):
        i["rank"] = n + 1

    logger.info("Category '%s': %d items, S=%d A=%d B=%d",
                cat, len(result),
                sum(1 for i in result if i["importance"] == "S"),
                sum(1 for i in result if i["importance"] == "A"),
                sum(1 for i in result if i["importance"] == "B"))

    _run_auto_translate(result, cat)
    if cat == "ai":
        _AI_SOURCE_FAILURES.clear(); _AI_SOURCE_FAILURES.update(failures)
        _AI_SOURCE_COUNTS.clear(); _AI_SOURCE_COUNTS.update(counts)
        logger.info("AI source health: total=%d success=%d failed=%d", len(feeds), len(feeds)-len(failures), len(failures))
    return result
def save_news(cat, items):
    fp = config.AI_DATA_FILE if cat == "ai" else config.GAMING_DATA_FILE
    if cat == "ai" and _AI_SOURCE_FAILURES and os.path.exists(fp):
        try:
            with open(fp, "r", encoding="utf-8") as old_f:
                old_items = json.load(old_f).get("items", [])
            current_ids = {i.get("id") for i in items}
            items = list(items) + [i for i in old_items if i.get("source_name") in _AI_SOURCE_FAILURES and i.get("id") not in current_ids]
        except (OSError, ValueError, TypeError):
            pass
    payload = {
            "category": cat,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total": len(items),
            "items": items,
        }
    directory = os.path.dirname(fp) or "."
    fd, tmp = tempfile.mkstemp(prefix=".news_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, fp)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def refresh_all():
    for cat in ("ai", "gaming"):
        logger.info("Refreshing: %s", cat)
        items = fetch_category(cat)
        if len(items) > 0:
            save_news(cat, items)
        else:
            logger.warning("No items fetched for '%s', keeping existing data", cat)
    # Build gaming hotspots after refresh
    try:
        from game_hotspot import build_game_hotspots
        hotspots = build_game_hotspots()
        logger.info("Gaming hotspots: %d", len(hotspots))
    except Exception as e:
        logger.warning("Hotspot build failed: %s", e)
    return True


# ---------- AI Processing State ----------




def _merge_ai_fields(new_item, insight_map):
    iid = new_item["id"]
    if iid in insight_map:
        new_item["ai_status"] = insight_map[iid]["status"]
    else:
        new_item["ai_status"] = "none"


# ---------- AI Insights ----------
AI_INSIGHTS_FILE = os.path.join(os.path.dirname(__file__), "data", "ai_insights.json")

def _load_ai_insights():
    try:
        with open(AI_INSIGHTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_ai_insights(data):
    with open(AI_INSIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _get_insight_map():
    return {i["article_id"]: i for i in _load_ai_insights()}

def _update_ai_insight(article_id, updates):
    insights = _load_ai_insights()
    for i, ins in enumerate(insights):
        if ins["article_id"] == article_id:
            insights[i].update(updates)
            _save_ai_insights(insights)
            return insights[i]
    entry = {"article_id": article_id, "status": "pending", "generated_time": None,
             "ai_title": "", "summary": "", "key_points": [], "industry_impact": ""}
    entry.update(updates)
    insights.append(entry)
    _save_ai_insights(insights)
    return entry


if __name__ == "__main__":
    refresh_all()
    print("Done.")
