"""Group articles that describe the same event.

Google News links are opaque redirects, so URL matching is useless for cross-outlet
duplicates. We cluster on text similarity instead:

  * tokens from the headline (weighted double) plus the opening of the summary,
  * weighted by inverse document frequency, so rare words — names, places,
    companies — decide matches and filler words don't,
  * normalised by the *smaller* of the two token sets, so a terse headline can
    still match a wordy one about the same event,
  * then a second pass that merges clusters which turned out to be the same story.

An inverted index keeps this from being an all-pairs comparison.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from math import log as ln
from typing import Dict, List, Set, Tuple

from .config import config
from .models import Article, Cluster

log = logging.getLogger(__name__)

STOPWORDS: Set[str] = {
    "the", "a", "an", "and", "or", "but", "for", "of", "to", "in", "on", "at", "by",
    "with", "from", "as", "is", "are", "was", "were", "be", "been", "being", "it",
    "its", "this", "that", "these", "those", "his", "her", "their", "our", "you",
    "we", "how", "why", "what", "when", "who", "will", "can", "could", "would",
    "should", "after", "before", "into", "over", "about", "more", "than", "new",
    "says", "say", "said", "report", "reports", "reported", "amid", "against", "up",
    "down", "out", "off", "not", "has", "have", "had", "may", "might", "first",
    "top", "big", "one", "two", "now", "also", "still", "just", "get", "gets",
    "make", "makes", "take", "takes", "year", "years", "day", "days", "week",
    "month", "time", "today", "than", "they", "them", "there", "here", "which",
    "while", "some", "all", "any", "his", "she", "him", "per", "cent", "percent",
}

_TOKEN_RE = re.compile(r"[a-z0-9']+")
TITLE_BOOST = 2.0
SUMMARY_CHARS = 320  # only the opening of a summary is reliably about the event


def normalise(title: str) -> str:
    title = title.lower()
    title = re.sub(r"^(exclusive|breaking|update\s*\d*|analysis|opinion|live|watch)\s*[:\-–]\s*", "", title)
    title = re.sub(r"[’'`]", "", title)
    return re.sub(r"[^a-z0-9 ]+", " ", title).strip()


def tokenise(text: str) -> Set[str]:
    return {t for t in _TOKEN_RE.findall(normalise(text)) if len(t) > 2 and t not in STOPWORDS}


def signature(article: Article) -> Dict[str, float]:
    """Token -> local weight. Headline tokens count for more than summary tokens."""
    weights: Dict[str, float] = {}
    for token in tokenise(article.title):
        weights[token] = TITLE_BOOST
    for token in tokenise(article.summary[:SUMMARY_CHARS]):
        weights.setdefault(token, 1.0)
    return weights


def _idf(signatures: List[Dict[str, float]]) -> Dict[str, float]:
    counts: Counter = Counter()
    for sig in signatures:
        counts.update(sig.keys())
    total = max(len(signatures), 1)
    return {token: ln(1 + total / count) for token, count in counts.items()}


def _mass(sig: Dict[str, float], idf: Dict[str, float]) -> float:
    return sum(weight * idf.get(token, 1.0) for token, weight in sig.items())


def similarity(a: Dict[str, float], b: Dict[str, float], idf: Dict[str, float]) -> Tuple[float, int]:
    """Containment score in [0,1] plus the count of shared distinctive tokens."""
    shared = set(a) & set(b)
    if not shared:
        return 0.0, 0
    shared_mass = sum(min(a[t], b[t]) * idf.get(t, 1.0) for t in shared)
    denominator = min(_mass(a, idf), _mass(b, idf))
    if denominator <= 0:
        return 0.0, 0
    distinctive = sum(1 for t in shared if idf.get(t, 0.0) >= 1.6)
    return min(shared_mass / denominator, 1.0), distinctive


def _merge_signature(target: Dict[str, float], extra: Dict[str, float]) -> None:
    for token, weight in extra.items():
        target[token] = max(target.get(token, 0.0), weight)


def cluster_articles(articles: List[Article], threshold: float = None) -> List[Cluster]:
    threshold = config.dedupe_threshold if threshold is None else threshold
    if not articles:
        return []

    ordered = sorted(articles, key=lambda a: (-a.feed_weight, a.published))
    signatures = [signature(a) for a in ordered]
    idf = _idf(signatures)

    clusters: List[Cluster] = []
    cluster_sigs: List[Dict[str, float]] = []
    index: Dict[str, Set[int]] = defaultdict(set)  # token -> cluster indices

    for article, sig in zip(ordered, signatures):
        if not sig:
            continue
        # Only consider clusters that share a reasonably distinctive token.
        candidates: Counter = Counter()
        for token in sig:
            if idf.get(token, 0.0) < 1.2:
                continue
            for cluster_index in index[token]:
                candidates[cluster_index] += 1

        best_index, best_score = -1, 0.0
        for cluster_index, overlap in candidates.items():
            if overlap < 2:
                continue
            score, distinctive = similarity(sig, cluster_sigs[cluster_index], idf)
            if distinctive < 2 and score < 0.75:
                continue
            if score < threshold:
                continue
            if score > best_score:
                best_index, best_score = cluster_index, score

        if best_index >= 0:
            clusters[best_index].articles.append(article)
            _merge_signature(cluster_sigs[best_index], sig)
            for token in sig:
                if idf.get(token, 0.0) >= 1.2:
                    index[token].add(best_index)
        else:
            clusters.append(Cluster(articles=[article]))
            cluster_sigs.append(dict(sig))
            new_index = len(clusters) - 1
            for token in sig:
                if idf.get(token, 0.0) >= 1.2:
                    index[token].add(new_index)

    before = len(clusters)
    clusters = _merge_pass(clusters, cluster_sigs, idf, threshold)
    log.info("Clustered %d articles into %d stories (%d merged on second pass)",
             len(articles), len(clusters), before - len(clusters))
    return clusters


def _merge_pass(clusters, cluster_sigs, idf, threshold):
    """Second look: clusters built early can end up describing the same event.

    Candidate pairs come from an inverted index, so this stays near-linear.
    """
    index: Dict[str, Set[int]] = defaultdict(set)
    for i, sig in enumerate(cluster_sigs):
        for token in sig:
            if idf.get(token, 0.0) >= 1.2:
                index[token].add(i)

    merged_into: Dict[int, int] = {}
    for i in range(len(clusters)):
        if i in merged_into:
            continue
        candidates: Counter = Counter()
        for token in cluster_sigs[i]:
            if idf.get(token, 0.0) < 1.2:
                continue
            for j in index[token]:
                if j > i:
                    candidates[j] += 1

        for j, overlap in candidates.items():
            if j in merged_into or overlap < 2:
                continue
            score, distinctive = similarity(cluster_sigs[i], cluster_sigs[j], idf)
            if score >= threshold and distinctive >= 2:
                clusters[i].articles.extend(clusters[j].articles)
                _merge_signature(cluster_sigs[i], cluster_sigs[j])
                merged_into[j] = i

    return [c for i, c in enumerate(clusters) if i not in merged_into]
