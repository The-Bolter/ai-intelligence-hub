"""
Translation service layer using translators library.

Provides article-level translation for the news-dashboard.
Currently wraps the translators library with Google as default backend.
"""

import os
import json
import logging
from datetime import datetime, timezone

# Prevent translators from doing network calls at import time.
# Actual translation calls still require network access (use escalated permissions).
os.environ.setdefault("translators_default_region", "EN")

import rules

logger = logging.getLogger(__name__)

# Default translator backend
_TRANSLATOR = os.getenv("TRANSLATION_PROVIDER", "google")
_TARGET_LANG = "zh"
_SOURCE_LANG = "auto"


def translate_text(text: str) -> str:
    """Translate English text to Chinese.

    Args:
        text: English text to translate.

    Returns:
        Chinese translation string, or empty string on failure.
    """
    if not text or not text.strip():
        return ""

    try:
        # Import lazily: translators performs a network region probe at import
        # time, which must not make the dashboard fail when offline.
        import translators as ts
        result = ts.translate_text(
            text,
            translator=_TRANSLATOR,
            from_language=_SOURCE_LANG,
            to_language=_TARGET_LANG,
        )
        return result
    except Exception as exc:
        logger.warning(
            "translate_text failed [translator=%s from=%s to=%s]: %s",
            _TRANSLATOR, _SOURCE_LANG, _TARGET_LANG, exc,
            exc_info=True,
        )
        raise


def translate_article(title: str, summary: str = "") -> dict:
    """Translate an article's title and summary to Chinese.

    Args:
        title:   English title of the article.
        summary: English summary/description (optional).

    Returns:
        dict with keys:
            title_cn:    Chinese translation of the title.
            summary_cn:  Chinese translation of the summary.
            status:      "translated" when at least one field succeeded,
                         "failed" when both fields failed.
            error:       (only on failure) description of what went wrong.
    """
    title_cn = ""
    summary_cn = ""
    err = None

    try:
        title_cn = translate_text(title)
    except Exception as e:
        err = str(e)
        print("TRANSLATION ERROR (title):", repr(e))

    if summary:
        try:
            summary_cn = translate_text(summary)
        except Exception as e:
            if err is None:
                err = str(e)
            print("TRANSLATION ERROR (summary):", repr(e))

    status = "translated" if (title_cn or summary_cn) else "failed"
    result = {"title_cn": title_cn, "summary_cn": summary_cn, "status": status}
    if err:
        result["error"] = err
    return result

# ---- Cache Layer ----

_TRANSLATIONS_PATH = None


def _get_translations_path() -> str:
    """Lazy-resolve the path to data/translations.json."""
    global _TRANSLATIONS_PATH
    if _TRANSLATIONS_PATH is None:
        base = os.path.dirname(os.path.abspath(__file__))
        _TRANSLATIONS_PATH = os.path.join(base, "data", "translations.json")
    return _TRANSLATIONS_PATH


def _load_translations() -> dict:
    """Load all cached translations from disk.

    Returns:
        dict of {article_id: translation_entry}.
    """
    path = _get_translations_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load translations cache: %s", exc)
        return {}


def _save_translations(data: dict) -> None:
    """Persist the full translations cache to disk."""
    path = _get_translations_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.error("Failed to save translations cache: %s", exc)


def get_cached_translation(article_id: str) -> dict | None:
    """Retrieve a cached translation by article_id.

    Args:
        article_id: Unique identifier for the article.

    Returns:
        Translation dict or None if not cached.
    """
    cache = _load_translations()
    return cache.get(article_id)


def translate_and_cache(article_id: str, title: str, summary: str = "") -> dict:
    """Translate an article and persist the result to the cache.

    If the article_id is already cached, returns the cached result
    without re-translating (zero token cost).

    Args:
        article_id: Unique identifier for deduplication.
        title:      English title.
        summary:    English summary (optional).

    Returns:
        Translation dict with keys:
            article_id, title_cn, summary_cn, status, generated_time.
    """
    # 1. Check cache first
    cached = get_cached_translation(article_id)
    if cached is not None:
        logger.debug("Translation cache hit: %s", article_id)
        return cached

    # 2. Translate
    result = translate_article(title, summary)

    # 3. Enrich with metadata
    result["article_id"] = article_id
    result["generated_time"] = datetime.now(timezone.utc).isoformat()

    # 4. Persist
    cache = _load_translations()
    cache[article_id] = result
    _save_translations(cache)

    logger.debug("Translation cached: %s", article_id)
    return result


def get_translation_stats() -> dict:
    """Return summary statistics about the translation cache.

    Returns:
        dict with keys: total, translated, failed, pending.
    """
    cache = _load_translations()
    entries = list(cache.values())
    total = len(entries)
    translated = sum(1 for e in entries if e.get("status") == "translated")
    failed = sum(1 for e in entries if e.get("status") == "failed")
    return {
        "total": total,
        "translated": translated,
        "failed": failed,
        "pending": total - translated - failed,
    }


# ---- Filter Helpers ----

def is_chinese_text(text: str) -> bool:
    """Check whether text is primarily Chinese (>30 % Han characters).

    Args:
        text: Input string to check.

    Returns:
        True if at least 30 % of characters are CJK Unified Ideographs.
    """
    if not text:
        return False
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return chinese / max(len(text), 1) >= 0.30


def is_valid_summary(summary: str) -> bool:
    """Check whether a summary has meaningful content for translation.

    Filters out:
      - Empty or too-short text (< 20 chars)
      - Hacker-News-style metadata (URLs + comment links + point counts)
      - Content that is majority URLs

    Args:
        summary: Article summary / description.

    Returns:
        True if the summary looks like real content worth translating.
    """
    if not summary or len(summary.strip()) < 20:
        return False

    text = summary.strip().lower()

    # HN / RSS metadata pattern: multiple URLs + point/comment markers
    hn_patterns = ["article url:", "comments url:", "# comments", "points:"]
    hn_hits = sum(1 for p in hn_patterns if p in text)
    if hn_hits >= 2 and len(text) < 300:
        return False

    # Estimate URL footprint
    url_markers = ["http://", "https://", "www."]
    url_chars = sum(text.count(m) * 30 for m in url_markers)
    if url_chars > len(text) * 0.5 and hn_hits >= 1:
        return False

    return True


def try_translate_article(
    article_id: str,
    title: str,
    summary: str = "",
) -> dict:
    """Filter-driven translation entry point.

    Steps:
      1. If the title is already Chinese → skip with reason.
      2. If the summary is not meaningful     → skip with reason.
      3. Otherwise                            → translate & cache.

    This is the function that external code should call when it wants
    to translate an article.  Auto-translation triggers will route
    through here so that the filtering is always applied.

    Args:
        article_id: Unique article identifier.
        title:      Article title.
        summary:    Article summary / description (optional).

    Returns:
        Translation dict.  Status is one of:
          "translated"  — success (from translate_and_cache)
          "skip"        — skipped because of language or content filters
          "failed"      — translation itself failed
    """
    if is_chinese_text(title):
        return {
            "article_id": article_id,
            "title_cn": title,
            "summary_cn": "",
            "status": "skip",
            "reason": "already_chinese",
        }

    if not is_valid_summary(summary):
        return {
            "article_id": article_id,
            "title_cn": "",
            "summary_cn": "",
            "status": "skip",
            "reason": "invalid_summary",
        }

    return translate_and_cache(article_id, title, summary)


# ---- Trigger Rules ----

def should_translate(article: dict) -> bool:
    """Determine whether an article should be automatically translated.

    AI trigger rules:
      - importance in ("S", "A")
      - or value_score >= TRANSLATION_POLICY["min_value_score"]
      - or source_priority >= TRANSLATION_POLICY["min_source_priority"]

    Args:
        article: Article dict containing at minimum:
                 importance, value_score, source_priority.

    Returns:
        bool: True if this article should be translated automatically.
    """
    policy = rules.TRANSLATION_POLICY
    if article.get("importance") in policy.get("importance_levels", ("S", "A")):
        return True
    if article.get("value_score", 0) >= policy.get("min_value_score", 60):
        return True
    if article.get("source_priority", 0) >= policy.get("min_source_priority", 8):
        return True
    return False
