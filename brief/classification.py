"""Assign each cluster to exactly one section.

Two inputs: which feeds the articles came from (a soft prior) and how strongly the
text matches each section's keyword list. Highest score wins; every cluster lands
in one section only, which is what stops a story appearing twice in the brief.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List

from .config import config
from .feeds import SECTION_KEYWORDS
from .models import Cluster

log = logging.getLogger(__name__)

FEED_PRIOR = 1.5  # how much the originating feed's own section counts for


# Whole-word matching matters more than it looks: plain substring matching lets
# "agi" fire on "against" and "ai" on "said", which quietly poisons the sections.
_KEYWORD_PATTERNS: Dict[str, List] = {
    section: [(re.compile(r"\b{}\b".format(re.escape(kw)), re.I), weight)
              for kw, weight in keywords.items()]
    for section, keywords in SECTION_KEYWORDS.items()
}


def keyword_score(text: str, section: str) -> float:
    return sum(weight for pattern, weight in _KEYWORD_PATTERNS[section] if pattern.search(text))


def section_scores(cluster: Cluster) -> Dict[str, float]:
    text = cluster.combined_text
    scores = {section: keyword_score(text, section) for section in SECTION_KEYWORDS}
    for article in cluster.articles:
        if article.feed_section in scores and not article.is_discovery:
            scores[article.feed_section] += FEED_PRIOR
        elif article.feed_section in scores:
            scores[article.feed_section] += FEED_PRIOR * 0.5
    return scores


def classify(clusters: List[Cluster], funding_ids: set) -> Dict[str, List[Cluster]]:
    """funding_ids: id()s of clusters already claimed by the funding radar."""
    buckets: Dict[str, List[Cluster]] = {s: [] for s in config.enabled_sections}

    for cluster in clusters:
        text = cluster.combined_text
        if id(cluster) in funding_ids:
            cluster.section = "funding"
            buckets.setdefault("funding", []).append(cluster)
            continue

        scores = section_scores(cluster)
        # Funding is handled by its own extractor; don't let it win here.
        scores.pop("funding", None)
        candidates = {s: v for s, v in scores.items() if s in buckets}
        if not candidates:
            continue
        best = max(candidates, key=candidates.get)
        # The feed a story arrived on is only a hint. Without keyword evidence in the
        # text itself we drop it, which is what keeps off-topic Google News hits out.
        if keyword_score(text, best) < config.min_section_evidence:
            continue
        cluster.section = best
        cluster.score_breakdown["keywords"] = candidates[best]
        buckets[best].append(cluster)

    for section, items in buckets.items():
        log.info("Section %-11s %3d stories", section, len(items))
    return buckets
