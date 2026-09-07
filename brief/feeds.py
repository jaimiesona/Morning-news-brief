"""Feed catalogue: trusted anchor RSS feeds + Google News RSS discovery queries.

Add or remove entries here to retune the brief. `weight` is a rough editorial
trust/signal score used by ranking.py (higher = more likely to be a real story).
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Dict, List

from .config import config

SECTIONS: Dict[str, str] = {
    "ai": "Latest AI developments",
    "politics": "Global politics",
    "technology": "World technology",
    "funding": "Startup funding radar",
}


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    section: str  # the section this feed is *biased* towards, not a hard assignment
    weight: float = 1.0
    kind: str = "anchor"  # "anchor" or "discovery"


def google_news_rss(query: str) -> str:
    """Build a Google News RSS search URL. `when:1d` limits to roughly the last day."""
    params = {
        "q": query,
        "hl": config.google_news_language,
        "gl": config.google_news_country,
        "ceid": config.google_news_locale,
    }
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


# --- Anchor feeds: publishers with stable, free, full RSS -------------------
ANCHOR_FEEDS: List[Feed] = [
    # AI
    Feed("Ars Technica AI", "https://feeds.arstechnica.com/arstechnica/technology-lab", "ai", 1.8),
    Feed("MIT Technology Review", "https://www.technologyreview.com/feed/", "ai", 1.8),
    Feed("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", "ai", 1.2),
    Feed("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "ai", 1.5),
    Feed("Google DeepMind Blog", "https://deepmind.google/blog/rss.xml", "ai", 1.6),
    Feed("OpenAI News", "https://openai.com/news/rss.xml", "ai", 1.6),
    Feed("Hugging Face Blog", "https://huggingface.co/blog/feed.xml", "ai", 1.1),
    Feed("Import AI", "https://importai.substack.com/feed", "ai", 1.3),
    Feed("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "ai", 1.5),
    Feed("The Decoder", "https://the-decoder.com/feed/", "ai", 1.4),
    Feed("Simon Willison", "https://simonwillison.net/atom/everything/", "ai", 1.2),

    # Politics / world
    Feed("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "politics", 1.9),
    Feed("Guardian World", "https://www.theguardian.com/world/rss", "politics", 1.7),
    Feed("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "politics", 1.5),
    Feed("Deutsche Welle Top", "https://rss.dw.com/rdf/rss-en-top", "politics", 1.4),
    Feed("France 24 World", "https://www.france24.com/en/rss", "politics", 1.3),
    Feed("Politico EU", "https://www.politico.eu/feed/", "politics", 1.5),
    Feed("NPR World", "https://feeds.npr.org/1004/rss.xml", "politics", 1.4),
    Feed("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "politics", 1.2),
    Feed("New York Times World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "politics", 1.7),
    Feed("Guardian UK Politics", "https://www.theguardian.com/politics/rss", "politics", 1.4),
    Feed("Sky News World", "https://feeds.skynews.com/feeds/rss/world.xml", "politics", 1.3),

    # Technology (non-AI)
    Feed("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "technology", 1.7),
    Feed("The Verge", "https://www.theverge.com/rss/index.xml", "technology", 1.4),
    Feed("The Register", "https://www.theregister.com/headlines.atom", "technology", 1.3),
    Feed("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "technology", 1.6),
    Feed("Hacker News (front page)", "https://hnrss.org/frontpage?points=150", "technology", 1.1),
    Feed("Krebs on Security", "https://krebsonsecurity.com/feed/", "technology", 1.5),
    Feed("BleepingComputer", "https://www.bleepingcomputer.com/feed/", "technology", 1.2),
    Feed("NASA Breaking News", "https://www.nasa.gov/news-release/feed/", "technology", 1.3),
    Feed("SpaceNews", "https://spacenews.com/feed/", "technology", 1.2),
    Feed("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "technology", 1.3),
    Feed("New York Times Tech", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "technology", 1.6),
    Feed("Ars Technica Policy", "https://feeds.arstechnica.com/arstechnica/tech-policy", "technology", 1.5),
    Feed("Engadget", "https://www.engadget.com/rss.xml", "technology", 1.2),
    Feed("Wired", "https://www.wired.com/feed/rss", "technology", 1.4),
    Feed("CNBC Technology", "https://www.cnbc.com/id/19854910/device/rss/rss.html", "technology", 1.3),

    # Startups / funding
    Feed("TechCrunch", "https://techcrunch.com/feed/", "funding", 1.5),
    Feed("TechCrunch Venture", "https://techcrunch.com/category/venture/feed/", "funding", 1.6),
    Feed("EU-Startups", "https://www.eu-startups.com/feed/", "funding", 1.6),
    Feed("Tech.eu", "https://tech.eu/feed/", "funding", 1.6),
    Feed("UKTN", "https://www.uktech.news/feed", "funding", 1.4),
    Feed("Silicon Canals", "https://siliconcanals.com/feed/", "funding", 1.3),
    Feed("Sifted", "https://sifted.eu/feed", "funding", 1.5),
    Feed("TechCrunch Startups", "https://techcrunch.com/category/startups/feed/", "funding", 1.4),
]

# --- Discovery queries: Google News RSS -------------------------------------
# Kept deliberately specific; broad queries return mostly noise.
DISCOVERY_QUERIES: Dict[str, List[str]] = {
    "ai": [
        '("artificial intelligence" OR "AI model") (launch OR release OR announces) when:1d',
        '(OpenAI OR Anthropic OR "Google DeepMind" OR Meta AI OR Mistral) when:1d',
        '("AI regulation" OR "AI act" OR "AI safety" OR "AI policy") when:1d',
        '(Nvidia OR TSMC OR "AI chips" OR "AI data centre" OR "AI data center") when:1d',
        '("AI acquisition" OR "AI startup acquired" OR "AI research paper") when:1d',
    ],
    "politics": [
        '(election OR "election results" OR "general election") when:1d',
        '(sanctions OR ceasefire OR "peace talks" OR "diplomatic") when:1d',
        '("trade deal" OR tariffs OR "trade dispute" OR WTO) when:1d',
        '(parliament OR summit OR "prime minister" OR president) international when:1d',
        '(conflict OR military OR "border" OR "airstrike") when:1d',
    ],
    "technology": [
        '(semiconductor OR chipmaker OR "export controls") when:1d',
        '(cyberattack OR "data breach" OR ransomware OR vulnerability) when:1d',
        '("space launch" OR satellite OR rocket OR ESA OR SpaceX) when:1d',
        '(Apple OR Microsoft OR Google OR Amazon OR Samsung) (launch OR antitrust OR fine) when:1d',
        '(robotics OR "quantum computing" OR "battery technology") when:1d',
    ],
    "funding": [
        '(startup "raises" OR "raised") ("Series A" OR "Series B" OR seed) when:1d',
        '(UK OR London OR British) startup funding round when:1d',
        '(European OR Europe) startup "raises" million when:1d',
        '("pre-seed" OR "seed funding" OR "Series C") "led by" when:1d',
        '(startup "secures" funding OR "closes" funding round) when:1d',
    ],
}

# Keywords that push a story towards a section, and mark it as high-signal.
SECTION_KEYWORDS: Dict[str, Dict[str, float]] = {
    "ai": {
        "artificial intelligence": 3, "ai": 2.0, "llm": 3, "gpt": 2.5, "agentic": 2.5, "large language model": 3,
        "openai": 3, "anthropic": 3, "deepmind": 3, "gemini": 2.5, "claude": 2.5,
        "chatgpt": 2.5, "mistral": 2.5, "llama": 2, "hugging face": 2, "nvidia": 2.5,
        "gpu": 2, "inference": 2, "training run": 2.5, "foundation model": 3,
        "machine learning": 2.5, "neural network": 2.5, "agi": 2.5, "ai chip": 3,
        "ai regulation": 3, "ai act": 3, "ai safety": 3, "copilot": 1.5, "model weights": 2.5,
        "open-weight": 2.5, "benchmark": 1.5, "ai agent": 2.5, "data centre": 1.5,
        "generative ai": 3, "transformer": 1.5, "superintelligence": 3, "ai lab": 3,
    },
    "politics": {
        "election": 3, "parliament": 2.5, "president": 2, "prime minister": 2.5,
        "sanctions": 3, "ceasefire": 3, "treaty": 2.5, "diplomat": 2.5, "summit": 2,
        "tariff": 2.5, "trade deal": 2.5, "coalition": 2, "referendum": 2.5,
        "resign": 2, "coup": 3, "military": 2, "airstrike": 3, "invasion": 3,
        "nato": 2.5, "united nations": 2.5, "european union": 2, "legislation": 2,
        "protest": 1.5, "impeach": 2.5, "border": 1.5, "peace talks": 3, "vote": 1.5,
    },
    "technology": {
        "semiconductor": 3, "chipmaker": 3, "foundry": 2.5, "export controls": 2.5,
        "cyberattack": 3, "data breach": 3, "ransomware": 3, "vulnerability": 2.5,
        "zero-day": 3, "encryption": 2, "satellite": 2.5, "rocket": 2.5, "spacecraft": 2.5,
        "launch": 1, "quantum": 3, "robot": 2.5, "antitrust": 2.5, "regulator": 2,
        "acquisition": 2, "battery": 2, "electric vehicle": 2, "broadband": 1.5,
        "operating system": 1.5, "smartphone": 1.5, "open source": 1.5, "patent": 1.5,
    },
    "funding": {
        "raises": 3, "raised": 2.5, "seed funding": 3, "pre-seed": 3, "series a": 3,
        "series b": 3, "series c": 3, "series d": 3, "funding round": 3,
        "venture capital": 2.5, "backed by": 2, "led by": 1.5, "valuation": 2,
        "oversubscribed": 2, "secures": 1.5, "investment round": 2.5,
    },
}

# Titles containing these are almost always low-value for this brief.
NOISE_PATTERNS: List[str] = [
    "best deals", "deal of the day", "discount", "coupon", "prime day",
    "here's how to watch", "how to watch", "live blog", "live updates",
    "horoscope", "quiz", "recap", "spoilers", "review:", "hands-on:",
    "sponsored", "advertisement", "top 10 ", "best laptops", "best phones",
    "gift guide", "everything you need to know about", "opinion:", "podcast:",
    "webinar", "white paper", "whitepaper", "sponsored by", "in partnership with",
    "what to know", "explained: ", "the best ", "save on ", "our favourite",
    "watch live", "photos:", "video:", "weekly roundup", "week in review",
    "launches investigation into", "class action", "notifies consumers",
    "check expected", "pre-order date", "latest leak", "here is where",
    "price target", "should you buy", "stock to buy", "shares worth", "stock jumps",
    "critical metric", "better buy", "dumps over", "sells shares", "buy the dip",
    " etf", "etfs", "leveraged", "retail investors", "share price", "stock market",
    "shares surge", "shares slump", "stocks to watch", "analyst rating",
    "better investment", "which is a better", "what company is", "stock gains",
    "stock falls", "is a buy", "buy or sell", "dividend", "earnings call",
]


# Publishers that mostly produce share-price commentary. Google News surfaces a lot
# of it under technology queries and it is never what this brief is for.
BLOCKED_SOURCES: List[str] = [
    "motley fool", "fool.com", "zacks", "benzinga", "simply wall st", "insider monkey",
    "tipranks", "investing.com", "seeking alpha", "barchart", "24/7 wall st",
    "stocktwits", "marketbeat", "invezz", "the globe and mail", "gurufocus",
    "yahoo finance", "moomoo", "ad hoc news", "nasdaq", "tipranks", "stocktargets",
    "insider monkey", "financhill", "market screener", "sharecast",
]


def all_feeds() -> List[Feed]:
    """Anchor feeds plus one synthetic Feed per Google News discovery query."""
    feeds = [f for f in ANCHOR_FEEDS if f.section in config.enabled_sections]
    for section, queries in DISCOVERY_QUERIES.items():
        if section not in config.enabled_sections:
            continue
        for i, query in enumerate(queries, start=1):
            feeds.append(
                Feed(
                    name="Google News: {} #{}".format(section, i),
                    url=google_news_rss(query),
                    section=section,
                    weight=0.9,  # discovery is broad but noisy
                    kind="discovery",
                )
            )
    return feeds
