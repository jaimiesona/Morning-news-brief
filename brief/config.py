"""All tunable settings. Everything here can be overridden by environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional; GitHub Actions injects real env vars
    pass


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, "true" if default else "false").strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: str) -> List[str]:
    return [item.strip() for item in _env(name, default).split(",") if item.strip()]


@dataclass
class Config:
    # --- Collection ---------------------------------------------------------
    lookback_hours: int = _env_int("LOOKBACK_HOURS", 26)
    # If the normal window is too quiet (weekends, holidays) fall back to this one.
    fallback_lookback_hours: int = _env_int("FALLBACK_LOOKBACK_HOURS", 48)
    min_articles: int = _env_int("MIN_ARTICLES", 120)
    fetch_timeout: int = _env_int("FETCH_TIMEOUT", 20)
    fetch_workers: int = _env_int("FETCH_WORKERS", 8)
    # Article fetching: pulls the opening of the page for stories that make the brief.
    fetch_articles: bool = _env_bool("FETCH_ARTICLES", True)
    max_article_fetches: int = _env_int("MAX_ARTICLE_FETCHES", 30)
    article_timeout: int = _env_int("ARTICLE_TIMEOUT", 12)
    max_publisher_lookups: int = _env_int("MAX_PUBLISHER_LOOKUPS", 3)
    user_agent: str = _env(
        "USER_AGENT",
        "Mozilla/5.0 (compatible; MorningBriefBot/1.0; +https://github.com/)",
    )
    # Google News locale. GB:en gives UK-weighted results; US:en gives US-weighted.
    google_news_locale: str = _env("GOOGLE_NEWS_LOCALE", "GB:en")
    google_news_language: str = _env("GOOGLE_NEWS_LANGUAGE", "en-GB")
    google_news_country: str = _env("GOOGLE_NEWS_COUNTRY", "GB")

    # --- Sections -----------------------------------------------------------
    enabled_sections: List[str] = field(
        default_factory=lambda: _env_list("SECTIONS", "ai,politics,technology,funding")
    )
    max_stories_ai: int = _env_int("MAX_STORIES_AI", 6)
    max_stories_politics: int = _env_int("MAX_STORIES_POLITICS", 5)
    max_stories_technology: int = _env_int("MAX_STORIES_TECHNOLOGY", 5)
    max_funding_items: int = _env_int("MAX_FUNDING_ITEMS", 8)
    # Extra headlines listed as links only, under each section.
    max_extra_headlines: int = _env_int("MAX_EXTRA_HEADLINES", 4)

    # --- Region preference --------------------------------------------------
    # Stories mentioning these get a ranking boost (mainly used for funding).
    preferred_regions: List[str] = field(
        default_factory=lambda: _env_list(
            "PREFERRED_REGIONS",
            "uk,united kingdom,britain,london,europe,european,eu,ireland,germany,france,"
            "netherlands,spain,sweden,switzerland,denmark,finland,norway,poland,portugal,italy",
        )
    )
    region_boost: float = _env_float("REGION_BOOST", 2.0)

    # --- Deduplication / ranking -------------------------------------------
    dedupe_threshold: float = _env_float("DEDUPE_THRESHOLD", 0.30)
    corroboration_weight: float = _env_float("CORROBORATION_WEIGHT", 2.2)
    recency_weight: float = _env_float("RECENCY_WEIGHT", 2.0)
    keyword_weight: float = _env_float("KEYWORD_WEIGHT", 1.6)
    source_weight: float = _env_float("SOURCE_WEIGHT", 1.0)
    min_story_score: float = _env_float("MIN_STORY_SCORE", 0.0)
    # A story needs at least this much section-keyword evidence to be filed at all.
    min_section_evidence: float = _env_float("MIN_SECTION_EVIDENCE", 2.5)
    max_title_length: int = _env_int("MAX_TITLE_LENGTH", 150)

    # --- Summarisation ------------------------------------------------------
    # "extractive" = free, no LLM, quotes the source. "llm" = pluggable model backend.
    summariser: str = _env("SUMMARISER", "extractive")
    llm_provider: str = _env("LLM_PROVIDER", "anthropic")  # anthropic | openai_compatible
    llm_model: str = _env("LLM_MODEL", "claude-opus-5")
    llm_api_key: str = _env("LLM_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))
    llm_base_url: str = _env("LLM_BASE_URL", "")  # for openai_compatible / Ollama
    llm_effort: str = _env("LLM_EFFORT", "low")
    llm_max_stories: int = _env_int("LLM_MAX_STORIES", 20)
    llm_timeout: int = _env_int("LLM_TIMEOUT", 60)

    # --- Email --------------------------------------------------------------
    smtp_host: str = _env("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = _env_int("SMTP_PORT", 587)
    smtp_user: str = _env("SMTP_USER", "")
    smtp_password: str = _env("SMTP_PASSWORD", "")
    email_from: str = _env("EMAIL_FROM", "")
    email_to: List[str] = field(default_factory=lambda: _env_list("EMAIL_TO", ""))
    email_subject_prefix: str = _env("EMAIL_SUBJECT_PREFIX", "Morning Brief")

    # --- Output / behaviour -------------------------------------------------
    timezone: str = _env("TIMEZONE", "Europe/London")
    output_dir: str = _env("OUTPUT_DIR", "output")
    save_html: bool = _env_bool("SAVE_HTML", True)
    send_email: bool = _env_bool("SEND_EMAIL", True)
    log_level: str = _env("LOG_LEVEL", "INFO")

    def max_stories_for(self, section: str) -> int:
        return {
            "ai": self.max_stories_ai,
            "politics": self.max_stories_politics,
            "technology": self.max_stories_technology,
            "funding": self.max_funding_items,
        }.get(section, 5)

    def validate_email(self) -> List[str]:
        problems = []
        if not self.smtp_user:
            problems.append("SMTP_USER is not set")
        if not self.smtp_password:
            problems.append("SMTP_PASSWORD is not set")
        if not self.email_to:
            problems.append("EMAIL_TO is not set")
        return problems


config = Config()
