"""Score stories by importance, not just recency.

The single most useful free signal is corroboration: if six independent outlets
covered it in 24 hours, it matters more than something one blog posted.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List

from .config import config
from .classification import keyword_score
from .models import Cluster

log = logging.getLogger(__name__)


# Framing that usually signals gossip or filler rather than a development.
# Applied to the headline only, so it targets how a story is written up.
LOW_VALUE_PATTERNS = [
    (re.compile(r"\b(slams?|blasts?|hits? back|lashes? out|mocks?|shuts? down)\b", re.I), 1.2),
    (re.compile(r"\b(row|spat|feud|gaffe|backlash|outrage|fury) (over|about|at|with)\b", re.I), 1.2),
    (re.compile(r"\b(reportedly|rumou?r|allegedly|is said to|could soon)\b", re.I), 0.5),
    (re.compile(r"^(watch|listen|read|opinion|analysis)\b", re.I), 1.5),
    (re.compile(r"\b(here'?s|these are|why you should|what to expect)\b", re.I), 0.8),
]


def _low_value_penalty(title: str) -> float:
    return sum(penalty for pattern, penalty in LOW_VALUE_PATTERNS if pattern.search(title))


def _recency_factor(published: datetime) -> float:
    hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600.0
    if hours <= 6:
        return 1.0
    if hours >= config.lookback_hours:
        return 0.2
    return max(0.2, 1.0 - (hours - 6) / max(config.lookback_hours - 6, 1))


def _region_hit(text: str) -> bool:
    lowered = " {} ".format(text.lower())
    return any(region in lowered for region in config.preferred_regions)


def score_cluster(cluster: Cluster, section: str) -> float:
    distinct_sources = len({a.source.lower() for a in cluster.articles})
    corroboration = min(distinct_sources, 6) / 6.0
    best_source = max(a.feed_weight for a in cluster.articles)
    newest = max(a.published for a in cluster.articles)
    keywords = min(keyword_score(cluster.combined_text, section) / 12.0, 1.0)
    # Discovery-only stories are less trustworthy, but heavy corroboration earns
    # most of that trust back — otherwise real news that no anchor feed carried
    # gets buried under a single blog post from a weighted feed.
    if any(not a.is_discovery for a in cluster.articles):
        anchored = 1.0
    else:
        anchored = min(1.0, 0.55 + 0.12 * distinct_sources)

    score = (
        config.corroboration_weight * corroboration
        + config.source_weight * (best_source / 2.0)
        + config.keyword_weight * keywords
        + config.recency_weight * _recency_factor(newest)
    ) * anchored

    if section == "funding":
        item = cluster.score_breakdown.get("funding")
        # A round denominated in euros or sterling is a European round, even when
        # the headline never names a country.
        currency_hint = bool(item and item.amount and item.amount[0] in "£€")
        if currency_hint or _region_hit(cluster.lead.title) or (item and item.is_preferred_region):
            score += config.region_boost

    penalty = _low_value_penalty(cluster.lead.title)
    score -= penalty

    cluster.score_breakdown.update(
        {
            "sources": distinct_sources,
            "corroboration": round(corroboration, 2),
            "best_source_weight": best_source,
            "keywords": round(keywords, 2),
            "recency": round(_recency_factor(newest), 2),
            "anchored": anchored,
            "penalty": penalty,
        }
    )
    cluster.score = score
    return score


def rank(clusters: List[Cluster], section: str) -> List[Cluster]:
    for cluster in clusters:
        score_cluster(cluster, section)
    ranked = sorted(clusters, key=lambda c: -c.score)
    return [c for c in ranked if c.score >= config.min_story_score]
