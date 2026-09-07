"""Fetch and normalise RSS/Atom feeds.

Every feed is fetched independently; a failure is logged and skipped so one dead
feed can never take down the brief.
"""

from __future__ import annotations

import calendar
import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import feedparser
import requests

from .config import config
from .feeds import BLOCKED_SOURCES, Feed, NOISE_PATTERNS, all_feeds
from .models import Article

log = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# Tracking parameters we strip so the same article from two feeds looks identical.
_TRACKING_PREFIXES = ("utm_", "ito", "cmpid", "at_", "fbclid", "gclid", "ref", "s_")


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def canonical_url(url: str) -> str:
    """Normalise a URL for exact-duplicate detection (not for display)."""
    if not url:
        return ""
    try:
        parts = urlparse(url)
        query = [
            (k, v)
            for k, v in parse_qsl(parts.query)
            if not any(k.lower().startswith(p) for p in _TRACKING_PREFIXES)
        ]
        path = parts.path.rstrip("/") or "/"
        return urlunparse((parts.scheme.lower(), parts.netloc.lower(), path, "", urlencode(query), ""))
    except ValueError:
        return url


def _entry_datetime(entry) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
            except (ValueError, OverflowError, TypeError):
                continue
    return None


def _entry_source_url(entry) -> str:
    source = entry.get("source")
    if isinstance(source, dict):
        return str(source.get("href") or "")
    return ""


def _entry_source(entry, feed: Feed) -> str:
    """Google News wraps other publishers; recover the real one where possible."""
    source = entry.get("source")
    if isinstance(source, dict) and source.get("title"):
        return str(source["title"])
    if feed.kind == "discovery":
        # Google News titles end with " - Publisher".
        if " - " in entry.get("title", ""):
            return entry["title"].rsplit(" - ", 1)[-1].strip()
        return "Google News"
    return feed.name


def _clean_title(title: str, source: str) -> str:
    title = strip_html(title)
    suffix = " - {}".format(source)
    if source and title.endswith(suffix):
        title = title[: -len(suffix)].strip()
    return title


def _is_noise(title: str) -> bool:
    lowered = " {} ".format(title.lower())
    return any(pattern in lowered for pattern in NOISE_PATTERNS)


def _is_blocked_source(source: str) -> bool:
    lowered = source.lower()
    return any(blocked in lowered for blocked in BLOCKED_SOURCES)


def fetch_feed(feed: Feed, cutoff: datetime) -> List[Article]:
    headers = {"User-Agent": config.user_agent, "Accept": "application/rss+xml, application/xml, text/xml, */*"}
    try:
        response = requests.get(feed.url, headers=headers, timeout=config.fetch_timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Feed failed (%s): %s", feed.name, exc)
        return []

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        log.warning("Feed unparseable (%s): %s", feed.name, parsed.get("bozo_exception"))
        return []

    articles: List[Article] = []
    undated = 0
    for entry in parsed.entries:
        try:
            published = _entry_datetime(entry)
            if published is None:
                # Undated entries are usually fresh in a live feed, but we cannot
                # prove it — keep a few rather than silently inventing timestamps.
                undated += 1
                if undated > 3:
                    continue
                published = datetime.now(timezone.utc)
            if published < cutoff:
                continue

            raw_title = entry.get("title", "").strip()
            if not raw_title:
                continue
            source = _entry_source(entry, feed)
            if _is_blocked_source(source):
                continue
            title = _clean_title(raw_title, source)
            if not 15 <= len(title) <= config.max_title_length or _is_noise(title):
                continue

            link = entry.get("link") or ""
            if not link:
                continue

            summary = strip_html(entry.get("summary", "") or entry.get("description", ""))
            if not summary and entry.get("content"):
                summary = strip_html(entry["content"][0].get("value", ""))

            articles.append(
                Article(
                    title=title,
                    url=link,
                    source=source,
                    feed_name=feed.name,
                    feed_section=feed.section,
                    feed_weight=feed.weight,
                    published=published,
                    summary=summary[:1200],
                    is_discovery=feed.kind == "discovery",
                    summary_usable=feed.kind != "discovery",
                    source_url=_entry_source_url(entry),
                )
            )
        except Exception as exc:  # a single malformed entry must not kill the feed
            log.debug("Skipped bad entry in %s: %s", feed.name, exc)

    log.info("Fetched %-32s %3d articles", feed.name[:32], len(articles))
    return articles


def collect(feeds: Optional[List[Feed]] = None) -> List[Article]:
    """Fetch every feed in parallel and return de-duplicated-by-URL articles.

    Feeds are fetched once at the widest window we would ever accept, then filtered
    down. On a quiet morning (weekend, holiday) the narrow window is dropped in
    favour of the wide one — better a slightly older brief than an empty one.
    """
    feeds = feeds if feeds is not None else all_feeds()
    now = datetime.now(timezone.utc)
    wide_cutoff = now - timedelta(hours=max(config.lookback_hours, config.fallback_lookback_hours))
    cutoff = now - timedelta(hours=config.lookback_hours)

    articles: List[Article] = []
    with ThreadPoolExecutor(max_workers=config.fetch_workers) as pool:
        futures = {pool.submit(fetch_feed, feed, wide_cutoff): feed for feed in feeds}
        for future in as_completed(futures):
            feed = futures[future]
            try:
                articles.extend(future.result())
            except Exception as exc:
                log.warning("Unexpected error fetching %s: %s", feed.name, exc)

    recent = [a for a in articles if a.published >= cutoff]
    if len(recent) >= config.min_articles:
        articles = recent
    else:
        log.warning("Only %d articles in the last %dh — widening the window to %dh",
                    len(recent), config.lookback_hours, config.fallback_lookback_hours)

    seen = set()
    unique: List[Article] = []
    for article in sorted(articles, key=lambda a: (-a.feed_weight, a.is_discovery)):
        key = canonical_url(article.url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)

    log.info("Collected %d articles (%d after URL de-duplication)", len(articles), len(unique))
    return unique
