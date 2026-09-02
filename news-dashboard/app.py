# news-dashboard/app.py
# Flask 后端：提供新闻 API 和页面渲染

import json
import os
import threading
import time
import logging

from flask import Flask, jsonify, make_response, render_template, request, abort

import config
from fetcher import refresh_all, _load_ai_insights, _get_insight_map, _update_ai_insight
from translation_service import is_chinese_text, try_translate_article
from ai_today_view import build_ai_today_view
from gaming_collector import GamingCollector
from gaming_event_store import DEFAULT_EVENT_STORE_PATH, GamingEventStore
from gaming_weekly_v2 import build_today_new, build_weekly_radar

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

app.config["TEMPLATES_AUTO_RELOAD"] = True
GAMING_HOTSPOTS_FILE = os.path.join(os.path.dirname(__file__), "gaming_hotspots.json")
GAMING_EVENT_STORE_FILE = DEFAULT_EVENT_STORE_PATH
_AI_FRONT_PAGE_SECTIONS = (("today_priority", None), ("updates", 5), ("trends", 4), ("resources", 4))
_AI_TRANSLATION_PLACEHOLDERS = ("点击查看原文", "查看原文", "click to read", "read more")
_AUTO_REFRESH_THREAD = None
_AUTO_REFRESH_START_LOCK = threading.Lock()


def _translate_ai_front_page(view):
    """Fill only eligible cache misses currently rendered on the AI front page."""
    seen = set()
    for section, limit in _AI_FRONT_PAGE_SECTIONS:
        for article in (view.get(section) or [])[:limit]:
            article_id = str(article.get("id") or "").strip()
            summary = str(article.get("summary") or "").strip()
            existing = str(article.get("summary_cn") or article.get("chinese_summary") or "").strip()
            title = str(article.get("title") or "").strip()
            summary_lower = summary.lower()
            if (
                not article_id
                or article_id in seen
                or not summary
                or is_chinese_text(summary)
                or is_chinese_text(existing)
                or any(marker in summary_lower for marker in _AI_TRANSLATION_PLACEHOLDERS)
                or title.lower().startswith("show hn")
            ):
                continue
            seen.add(article_id)
            try_translate_article(article_id=article_id, title=title, summary=summary)


# ------------------ 后台自动刷新线程 ------------------

def _refresh_gaming_incremental():
    """Collect configured sources for games already tracked by the Event Store."""
    store = _load_gaming_event_store()
    game_ids = sorted({
        str(event.get("game_id") or "")
        for event in store.confirmed_events()
        if event.get("game_id")
    })
    if not game_ids:
        logger.info("Gaming incremental collection skipped: no tracked games.")
        return
    collector = GamingCollector()
    for game_id in game_ids:
        try:
            result = collector.collect_game_events(game_id)
            logger.info(
                "Gaming incremental collection complete: %s (%d sources, %d articles)",
                game_id, result["sources_checked"], result["articles_found"],
            )
        except Exception as exc:
            logger.error("Gaming incremental collection failed for %s: %s", game_id, exc)

def _auto_refresh_loop():
    while True:
        try:
            logger.info("Auto-refreshing all news...")
            refresh_all()
            logger.info("AI and legacy feed refresh complete.")
        except Exception as e:
            logger.error("AI and legacy feed refresh failed: %s", e)
        try:
            _refresh_gaming_incremental()
            logger.info("Gaming incremental refresh complete.")
        except Exception as e:
            logger.error("Gaming incremental refresh failed: %s", e)
        time.sleep(config.REFRESH_INTERVAL_MINUTES * 60)


def start_auto_refresh():
    global _AUTO_REFRESH_THREAD
    with _AUTO_REFRESH_START_LOCK:
        if _AUTO_REFRESH_THREAD and _AUTO_REFRESH_THREAD.is_alive():
            return
        _AUTO_REFRESH_THREAD = threading.Thread(target=_auto_refresh_loop, daemon=True)
        _AUTO_REFRESH_THREAD.start()
        logger.info("Auto-refresh thread started (interval: %d min)", config.REFRESH_INTERVAL_MINUTES)


@app.before_request
def _ensure_auto_refresh_started():
    """Flask CLI does not execute the module's __main__ startup block."""
    start_auto_refresh()


# ------------------ 数据读取 ------------------

def _load_news(category):
    file_path = config.AI_DATA_FILE if category == "ai" else config.GAMING_DATA_FILE
    if not os.path.exists(file_path):
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_gaming_hotspots():
    if not os.path.exists(GAMING_HOTSPOTS_FILE):
        return []
    try:
        with open(GAMING_HOTSPOTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("hotspots", []) or []
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to read gaming hotspots file: %s", GAMING_HOTSPOTS_FILE)
        return []


def _load_gaming_event_store():
    return GamingEventStore.load(GAMING_EVENT_STORE_FILE)


# ------------------ 路由 ------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/news")
def api_news():
    category = request.args.get("category", "").lower()
    if category not in ("ai", "gaming"):
        return jsonify({"error": "category must be 'ai' or 'gaming'"}), 400

    data = _load_news(category)
    if data is None:
        return jsonify({"error": "No data yet. Trigger a refresh first."}), 503
    return jsonify(data)


@app.route("/api/ai/today")
def api_ai_today():
    """Return a read-only, derived AI Today View from the cached AI feed."""
    data = _load_news("ai")
    if data is None:
        return jsonify({"error": "No data yet. Trigger a refresh first."}), 503
    view = build_ai_today_view(data.get("items", []))
    _translate_ai_front_page(view)
    return jsonify(build_ai_today_view(data.get("items", [])))


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    try:
        refresh_all()
        return jsonify({"status": "ok", "message": "News refreshed successfully"})
    except Exception as e:
        logger.error("Manual refresh error: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/status")
def api_status():
    ai_data = _load_news("ai")
    gaming_data = _load_news("gaming")
    return jsonify({
        "ai_loaded": ai_data is not None,
        "ai_count": ai_data["total"] if ai_data else 0,
        "ai_updated_at": ai_data["updated_at"] if ai_data else None,
        "gaming_loaded": gaming_data is not None,
        "gaming_count": gaming_data["total"] if gaming_data else 0,
        "gaming_updated_at": gaming_data["updated_at"] if gaming_data else None,
    })


# ------------------ 入口 ------------------




@app.route("/api/translations")
def api_translations():
    path = os.path.join(os.path.dirname(__file__), "data", "translations.json")
    if not os.path.exists(path):
        return jsonify({})
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)


@app.route("/api/test-translate", methods=["POST"])
def api_test_translate():
    data = request.get_json()
    article_id = data.get("article_id") if data else None
    if not article_id:
        return jsonify({"error": "article_id required"}), 400
    for cat in ("ai", "gaming"):
        news = _load_news(cat)
        if not news:
            continue
        for item in news.get("items", []):
            if item.get("id") == article_id:
                result = try_translate_article(
                    article_id=article_id,
                    title=item.get("title", ""),
                    summary=item.get("summary", ""),
                )
                if result.get("status") in ("failed", "skip"):
                    result["error"] = result.get("reason", "translation " + result["status"])
                if result.get("status") in ("failed", "skip"):
                    result["error"] = result.get("reason", "translation " + result["status"])
                return jsonify(result)
    return jsonify({"error": "article not found"}), 404

@app.route("/api/game-hotspots")
def api_game_hotspots():
    path = os.path.join(os.path.dirname(__file__), "data", "game_hotspots.json")
    if not os.path.exists(path):
        return jsonify({"total": 0, "games": []})
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    hotspots = data.get("hotspots", [])

    def priority(h):
        phase_rank = {"upcoming": 3, "active": 2, "ended": 1}
        level_rank = {"S": 4, "A": 3, "B": 2, "C": 1}
        return (
            phase_rank.get(h.get("phase", "ended"), 0),
            level_rank.get(h.get("hot_level", "C"), 0),
            h.get("hot_score", 0),
        )

    games = {}
    for h in hotspots:
        game = h.get("game_entity", "")
        if not game:
            continue
        games.setdefault(game, []).append(h)

    game_list = []
    for game, hs in games.items():
        hs.sort(key=priority, reverse=True)
        current = hs[0] if hs else None
        historical = hs[1:] if len(hs) > 1 else []
        total_articles = sum(len(h.get("articles", [])) for h in hs)
        game_list.append({
            "game_entity": game,
            "current_hotspot": current,
            "historical_hotspots": historical,
            "hotspot_count": len(hs),
            "total_articles": total_articles,
        })

    game_list.sort(
        key=lambda g: priority(g["current_hotspot"]) if g["current_hotspot"] else (0, 0, 0),
        reverse=True,
    )
    return jsonify({"total": len(game_list), "games": game_list})


@app.route("/api/gaming/hotspots")
def api_gaming_hotspots():
    game_id = request.args.get("game_id")
    event_type = request.args.get("event_type")
    items = []
    for h in _load_gaming_hotspots():
        if game_id and h.get("game_id") != game_id:
            continue
        if event_type and h.get("event_type") != event_type:
            continue
        items.append({
            "game_name": h.get("game_name") or "",
            "event_type": h.get("event_type") or "",
            "importance": h.get("importance") or "",
            "hotspot_score": h.get("hotspot_score", 0),
            "recommended_sources": h.get("recommended_sources") or [],
        })
    return jsonify({"items": items})


@app.route("/api/gaming/weekly")
def api_gaming_weekly():
    return jsonify(build_weekly_radar(_load_gaming_event_store()))


@app.route("/api/gaming/today-new")
def api_gaming_today_new():
    store = _load_gaming_event_store()
    weekly = build_weekly_radar(store)
    return jsonify(build_today_new(store, weekly_radar=weekly))

@app.route("/api/ai-insights")
def api_ai_insights():
    return jsonify({"insights": _load_ai_insights()})

@app.route("/api/ai-status")
def api_ai_status():
    insights = _get_insight_map()
    total = len(insights)
    completed = sum(1 for i in insights.values() if i["status"] == "completed")
    pending = sum(1 for i in insights.values() if i["status"] == "pending")
    return jsonify({"total": total, "completed": completed, "pending": pending})

@app.route("/api/ai-analyze", methods=["POST"])
def api_ai_analyze():
    data = request.get_json()
    article_id = data.get("article_id")
    if not article_id:
        return jsonify({"error": "article_id required"}), 400
    result = _update_ai_insight(article_id, {"status": "pending"})
    return jsonify({"status": "ok", "article_id": article_id})


# Explicit route registration (fallback)
app.add_url_rule("/api/ai-insights", view_func=api_ai_insights)
app.add_url_rule("/api/ai-status", view_func=api_ai_status)
app.add_url_rule("/api/ai-analyze", view_func=api_ai_analyze, methods=["POST"])

if __name__ == "__main__":
    logger.info("Starting news-dashboard server...")

    # 如果还没有数据，先抓一轮
    if not os.path.exists(config.AI_DATA_FILE) and not os.path.exists(config.GAMING_DATA_FILE):
        logger.info("No cached data found, fetching initial data...")
        refresh_all()

    start_auto_refresh()
    app.run(host="127.0.0.1", port=5678, debug=False)
