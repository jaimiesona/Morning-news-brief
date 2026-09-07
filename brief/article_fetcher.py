"""Fetch the opening of an article so the brief can say what a story is *about*.

RSS summaries are often missing, truncated, or (for Google News) not summaries at
all. For the handful of stories that actually make the brief we fetch the page and
take the publisher's own description and opening paragraphs.

Only articles with a real publisher URL can be fetched: Google News links are
redirects behind a consent wall and cannot be resolved server-side. Those stories
keep the headline-only treatment.
"""

from __future__ import annotations

import difflib
import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
from urllib.parse import urljoin

import requests

from .config import config
from .deduplication import tokenise
from .models import Article, Cluster

log = logging.getLogger(__name__)

_SCRIPT_RE = re.compile(r"<(script|style|noscript|template)[^>]*>.*?</\1>", re.S | re.I)
_PARA_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_META_TAG_RE = re.compile(r"<meta\s[^>]*>", re.I)
_ATTR_RE = re.compile(r'(\w[\w:-]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')
_DESCRIPTION_KEYS = ("og:description", "description", "twitter:description")

# Four or more capitalised words in a row is a navigation strip, not a sentence.
_NAV_RUN_RE = re.compile(r"(?:\b[A-Z][a-zA-Z]{1,14}\s+){4,}")
_ENGLISH_MARKERS = (" the ", " and ", " of ", " to ", " in ", " that ", " is ", " for ")

# Navigation and promo text that survives paragraph extraction on most news sites.
_BOILERPLATE = re.compile(
    r"(cookie|subscribe|newsletter|sign in|sign up|advertisement|all rights reserved|"
    r"follow us|share this|read more|privacy policy|terms of service|enable javascript|"
    r"your browser|posts from this topic|email digest|homepage feed|% off|tickets now|"
    r"take over \d|register now|watch on demand|download the app|comments?\)|"
    r"most popular|related stories|trending now|you might also|support our journalism|"
    r"thanks for liking|added it to a list|favou?rite stories|^close\b|"
    r"max-image-preview|max-snippet|name=|content=)",
    re.I,
)
_LINK_RE = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)
# How close a homepage link's text must be to the headline before we trust it.
HEADLINE_MATCH_THRESHOLD = 0.62


def _looks_like_prose(text: str) -> bool:
    words = text.split()
    if len(words) < 12:
        return False
    if "<" in text or ">" in text:
        return False
    if _NAV_RUN_RE.search(text):
        return False
    # Navigation blocks and section lists are mostly capitalised fragments.
    capitalised = sum(1 for w in words if w[:1].isupper())
    return capitalised / len(words) < 0.45


def _is_english(text: str) -> bool:
    """Cheap language check — a French or German page is worse than no page."""
    if len(text) < 200:
        return True
    lowered = " {} ".format(text.lower())
    return sum(lowered.count(marker) for marker in _ENGLISH_MARKERS) >= 4

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
MAX_BYTES = 400_000


def _meta_description(html: str) -> Optional[str]:
    """The publisher's own one-line description of the page, if it has one."""
    for tag in _META_TAG_RE.finditer(html[:120_000]):
        attrs = {}
        for match in _ATTR_RE.finditer(tag.group(0)):
            value = match.group(2) or match.group(3) or match.group(4) or ""
            attrs[match.group(1).lower()] = value
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key in _DESCRIPTION_KEYS:
            description = _clean(attrs.get("content", ""))
            if len(description) > 40:
                return description
    return None


def _clean(raw: str) -> str:
    # html.unescape handles every entity form — named (&amp;), decimal (&#39;) and
    # hex (&#x27;). A hand-written table always misses one, and the miss survives
    # into the email as visible markup.
    text = html.unescape(_TAG_RE.sub(" ", raw))
    return _WS_RE.sub(" ", text).strip()


def extract_text(html: str) -> str:
    """Publisher's own description, then the opening body paragraphs."""
    html = _SCRIPT_RE.sub(" ", html)
    parts: List[str] = []

    description = _meta_description(html)
    if description:
        parts.append(description)

    for match in _PARA_RE.finditer(html):
        paragraph = _clean(match.group(1))
        if len(paragraph) < 80 or _BOILERPLATE.search(paragraph):
            continue
        if not _looks_like_prose(paragraph):
            continue
        if any(paragraph[:60] == existing[:60] for existing in parts):
            continue
        parts.append(paragraph)
        if sum(len(p) for p in parts) > 900:
            break

    text = " ".join(parts)[:1500]
    return text if _is_english(text) else ""


def fetch_article(url: str) -> Optional[str]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml"},
            timeout=config.article_timeout,
            allow_redirects=True,
            stream=True,
        )
        response.raise_for_status()
        if "html" not in response.headers.get("Content-Type", "text/html").lower():
            return None
        html = response.raw.read(MAX_BYTES, decode_content=True).decode(
            response.encoding or "utf-8", errors="replace"
        )
    except Exception as exc:
        log.debug("Article fetch failed (%s): %s", url[:70], exc)
        return None
    finally:
        try:
            response.close()
        except Exception:
            pass

    text = extract_text(html)
    return text if len(text) > 120 else None


def resolve_via_publisher(domain: str, headline: str) -> Optional[str]:
    """Find an article URL by matching the headline against the publisher's homepage.

    Google News links cannot be resolved directly, but it does tell us which
    publisher ran the story. For a story big enough to be in the brief, the
    publisher's own front page almost always still links it. A high similarity
    threshold keeps this from grabbing an unrelated article.
    """
    if not domain or not domain.startswith("http"):
        return None
    try:
        response = requests.get(domain, headers={"User-Agent": BROWSER_UA},
                                timeout=config.article_timeout)
        response.raise_for_status()
        html = response.text[:MAX_BYTES]
    except Exception as exc:
        log.debug("Publisher homepage failed (%s): %s", domain, exc)
        return None

    target = headline.lower()[:90]
    best_url, best_score = None, 0.0
    for match in _LINK_RE.finditer(html):
        href, text = match.group(1), _clean(match.group(2))
        if len(text) < 20:
            continue
        score = difflib.SequenceMatcher(None, text.lower()[:90], target).ratio()
        if score > best_score:
            best_url, best_score = href, score

    if not best_url or best_score < HEADLINE_MATCH_THRESHOLD:
        return None
    resolved = urljoin(domain, best_url)
    # A link back to the front page tells us nothing about the story.
    if resolved.rstrip("/") == domain.rstrip("/"):
        return None
    return resolved


def _is_about_story(text: str, headline: str) -> bool:
    """Guard against fetching the wrong page.

    A resolved link can land on a section index or the site's front page, whose
    description is about the publication rather than the story. Requiring some of
    the headline's distinctive words to appear in the text catches that.
    """
    headline_tokens = {t for t in tokenise(headline) if len(t) > 3}
    if len(headline_tokens) < 2:
        return True
    lowered = text.lower()
    # Prefix matching so "intelligence" in the headline matches "intelligent" in
    # the body — news writing rarely repeats a word in exactly the same form.
    hits = sum(1 for token in headline_tokens
               if (token[:6] if len(token) > 6 else token) in lowered)
    return hits >= (2 if len(headline_tokens) >= 5 else 1)


def _needs_enrichment(cluster: Cluster) -> bool:
    """True when what we have is missing, stubby, or visibly truncated."""
    for article in cluster.articles:
        if article.full_text:
            return False
        if article.summary_usable and len(article.summary) >= 400:
            return False
    return True


def _fetchable(cluster: Cluster) -> Optional[Article]:
    """The best article in the cluster with a real, fetchable publisher URL."""
    candidates = [
        a for a in cluster.articles
        if a.url and "news.google.com" not in a.url and a.url.startswith("http")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda a: (not a.is_discovery, a.feed_weight))


def _enrich_cluster(cluster: Cluster) -> bool:
    """Get real text onto one cluster, by whichever route works."""
    article = _fetchable(cluster)
    if article:
        text = fetch_article(article.url)
        if text and _is_about_story(text, article.title):
            article.full_text = text
            return True

    # Google-only story: ask each publisher's front page where the article lives.
    tried = 0
    for candidate in cluster.sources:
        if not candidate.source_url or tried >= config.max_publisher_lookups:
            continue
        tried += 1
        url = resolve_via_publisher(candidate.source_url, candidate.title)
        if not url:
            continue
        text = fetch_article(url)
        if text and _is_about_story(text, candidate.title):
            candidate.full_text = text
            candidate.resolved_url = url
            return True
    return False


def enrich(clusters: List[Cluster]) -> int:
    """Fetch article text for the clusters that need it. Failures are silent."""
    targets = [c for c in clusters if _needs_enrichment(c)][: config.max_article_fetches]
    if not targets:
        return 0

    enriched = 0
    with ThreadPoolExecutor(max_workers=config.fetch_workers) as pool:
        futures = [pool.submit(_enrich_cluster, cluster) for cluster in targets]
        for future in as_completed(futures):
            try:
                if future.result():
                    enriched += 1
            except Exception as exc:
                log.debug("Enrichment error: %s", exc)

    log.info("Fetched article text for %d of %d stories", enriched, len(targets))
    return enriched
