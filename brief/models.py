"""Shared data structures passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Article:
    title: str
    url: str
    source: str            # publisher name (from the feed, or Google News <source>)
    feed_name: str
    feed_section: str
    feed_weight: float
    published: datetime     # timezone-aware UTC
    summary: str = ""       # plain text, stripped of HTML
    is_discovery: bool = False
    # Google News "descriptions" are a list of other outlets' headlines, not prose.
    # Useful for clustering, unusable as something to quote back to the reader.
    summary_usable: bool = True
    # Publisher homepage, supplied by Google News; used to find the real article.
    source_url: str = ""
    # Filled in by article_fetcher for stories that reach the brief.
    full_text: str = ""
    resolved_url: str = ""

    @property
    def best_url(self) -> str:
        """The link to show the reader: a real article URL beats a redirect."""
        return self.resolved_url or self.url

    @property
    def text(self) -> str:
        return "{} {}".format(self.title, self.summary)


@dataclass
class Cluster:
    """A group of articles believed to describe the same event."""

    articles: List[Article] = field(default_factory=list)
    section: Optional[str] = None
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)

    @property
    def lead(self) -> Article:
        """The best single article to represent the cluster.

        Prefers a known publisher with real summary text, and mildly prefers a
        headline of ordinary length — the outliers are section prefixes
        ("International Business: ...") and SEO padding.
        """

        def rank(article: Article) -> float:
            score = article.feed_weight * 3
            if not article.is_discovery:
                score += 5
            if article.summary_usable and article.summary:
                score += 3
            if ":" in article.title[:28] or " | " in article.title:
                score -= 2
            score -= abs(len(article.title) - 70) / 60.0
            return score

        return max(self.articles, key=rank)

    @property
    def title(self) -> str:
        return self.lead.title

    @property
    def sources(self) -> List[Article]:
        seen, out = set(), []
        for a in sorted(self.articles, key=lambda a: -a.feed_weight):
            key = a.source.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(a)
        return out

    @property
    def combined_text(self) -> str:
        parts = [self.lead.title]
        for a in self.articles:
            if a.summary:
                parts.append(a.summary)
        return "\n".join(parts)


@dataclass
class Story:
    """A ranked, summarised item ready for rendering."""

    headline: str
    what_happened: str
    simply_explained: str
    why_it_matters: str
    sources: List[Article]
    published: datetime
    score: float
    section: str
    funding: Optional["FundingItem"] = None


@dataclass
class FundingItem:
    """Fields are Optional on purpose: we only fill what the source text states."""

    company: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    amount: Optional[str] = None
    amount_usd: float = 0.0   # rough normalisation, used for ranking only
    stage: Optional[str] = None
    investors: List[str] = field(default_factory=list)
    is_preferred_region: bool = False


@dataclass
class Brief:
    generated_at: datetime
    sections: dict                      # section key -> List[Story]
    extra_headlines: dict               # section key -> List[Article]
    stats: dict = field(default_factory=dict)
    summariser_name: str = "extractive"
