"""Turn clusters into written stories.

Everything downstream depends only on the `Summariser` interface, so swapping the
free extractive backend for an LLM is a config change, not a rewrite.

  extractive : free, offline, quotes the source verbatim. Never fabricates because
               it never writes original prose about the facts.
  llm        : sends the collected source text to a model. Prompted to work only
               from that text and to say so when the text is insufficient.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from .config import config
from .glossary import find_terms
from .models import Cluster, Story

log = logging.getLogger(__name__)

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")

# Rule -> (weight, consequence). These describe the *category* of event we detected
# in the text; they assert nothing new about the story itself. Weights matter because
# a generic word like "launch" appears in almost any cluster of a dozen articles,
# so specific rules must be able to outrank it.
IMPACT_RULES = [
    (2.0, re.compile(r"\b(lawsuit|sues|suing|sued|copyright|court|ruling|judge|verdict|"
                     r"regulation|regulator|regulatory|legislation|antitrust|banned|fined)\b", re.I),
     "This is a rules story. Regulation and court decisions set the boundaries of what companies "
     "in the sector are allowed to build, sell or collect — the effects usually show up months later."),
    (2.0, re.compile(r"\b(acquisition|acquires|acquired|acquiring|merger|buyout|takeover|"
                     r"majority stake|minority stake|buys)\b", re.I),
     "Ownership is changing hands, which tends to reshape who controls a technology or market "
     "and what happens to the smaller company's products and customers."),
    (2.0, re.compile(r"\b(funding round|raises|raised|seed round|series [a-j]|valuation|"
                     r"venture capital|investors)\b", re.I),
     "Money moving into a company signals where investors think the next few years of growth are, "
     "and buys the company time to keep building."),
    (2.0, re.compile(r"\b(semiconductor|chipmaker|foundry|export controls|data cent(?:re|er)|"
                     r"gpus?|fabs?|lithography)\b", re.I),
     "This touches the physical supply chain underneath modern computing. Chip and data-centre "
     "constraints ripple outward into what everyone else can afford to build."),
    (2.5, re.compile(r"\b(breach|breached|hacked|hackers|ransomware|vulnerabilit\w+|exploit\w*|"
                     r"malware|cyberattack|zero-day)\b", re.I),
     "Security incidents rarely stay contained. The immediate question is who else uses the same "
     "software or service and is therefore exposed."),
    (2.0, re.compile(r"\b(election|elections|voters|ballot|parliament|coalition|resigns?|"
                     r"resignation|referendum|sworn in)\b", re.I),
     "Changes in who holds power move policy, spending and alliances, which is what makes domestic "
     "politics an international story."),
    (2.5, re.compile(r"\b(sanctions|tariffs?|trade war|embargo|export ban|trade deal)\b", re.I),
     "Economic pressure between states redirects trade flows and raises costs, usually for companies "
     "and consumers well outside the countries involved."),
    (2.5, re.compile(r"\b(airstrikes?|missiles?|invasion|ceasefire|troops|offensive|"
                     r"killed|casualties|war)\b", re.I),
     "Armed conflict drives energy prices, refugee movements and alliance commitments far beyond "
     "the immediate region."),
    (2.0, re.compile(r"\b(talks|negotiations|summit|envoys?|diplomat\w*|treaty|accord|"
                     r"agreement between)\b", re.I),
     "Diplomacy is where the next few months get decided. What is agreed — or not — here sets the "
     "conditions everything else in the region runs on."),
    (0.5, re.compile(r"\b(launches?|launched|releases?|released|unveils?|announces?|"
                     r"introduces?|rolls out)\b", re.I),
     "New capability arriving in public is what actually changes day-to-day tooling — worth noting "
     "what it can now do that the previous generation could not."),
]

DEFAULT_IMPACT = (
    "Multiple outlets picked this up within a day, which is the main signal that it is worth "
    "your attention. The sources below have the detail."
)


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if len(s.strip()) > 30]


class Summariser:
    """Interface. Implement `summarise_cluster` to add a new backend."""

    name = "base"

    def summarise(self, clusters: List[Cluster], section: str) -> List[Story]:
        return [self.summarise_cluster(cluster, section) for cluster in clusters]

    def summarise_cluster(self, cluster: Cluster, section: str) -> Story:
        raise NotImplementedError


class ExtractiveSummariser(Summariser):
    """No model, no API key, no cost. Reuses the publishers' own words."""

    name = "extractive"

    @staticmethod
    def _headline_fallback(cluster: Cluster) -> str:
        """Discovery-only stories have no prose to quote, so show how each outlet
        framed it. Still entirely the sources' words."""
        seen, angles = {cluster.lead.title.lower()}, []
        for article in cluster.sources[1:4]:
            if article.title.lower() in seen:
                continue
            seen.add(article.title.lower())
            angles.append("{} — \u201c{}\u201d".format(article.source, article.title))
        if not angles:
            return ("Only the headline reached the feeds for this one; the source link "
                    "below has the detail.")
        return "No summary text came through the feeds. How other outlets put it: " + "; ".join(angles) + "."

    def _what_happened(self, cluster: Cluster) -> str:
        candidates: List[str] = []
        # Fetched article text first: it is the publisher's actual opening, so it
        # says what a thing *is*, where a headline only says that it happened.
        for article in sorted(cluster.articles, key=lambda a: -len(a.full_text)):
            if not article.full_text:
                break
            candidates.extend(_sentences(article.full_text))
            break
        for article in sorted(cluster.articles, key=lambda a: -a.feed_weight):
            if not article.summary_usable:
                continue
            candidates.extend(_sentences(article.summary))
            if len(" ".join(candidates)) > 420:
                break
        if not candidates:
            return self._headline_fallback(cluster)
        picked, total = [], 0
        for sentence in candidates:
            if any(sentence[:60] == existing[:60] for existing in picked):
                continue
            picked.append(sentence)
            total += len(sentence)
            if total > 340 or len(picked) >= 3:
                break
        return " ".join(picked)

    def _simply_explained(self, cluster: Cluster, shown_text: str) -> str:
        # Scan what the reader can actually see, plus the lead article's own summary.
        # Scanning the whole cluster surfaces terms from articles that never appear
        # in the brief, which reads like a non-sequitur.
        terms = find_terms("{} {}".format(cluster.lead.title, shown_text))
        if terms:
            parts = ["<strong>{}</strong> — {}".format(term, meaning) for term, meaning in terms]
            return "Jargon in this story: " + "; ".join(parts) + "."
        return (
            "No specialist jargon detected here — the summary above is the whole of it, "
            "in ordinary language."
        )

    def _why_it_matters(self, cluster: Cluster) -> str:
        # Weight the headline heavily: across a dozen articles almost every rule
        # finds a stray match, and first-match-wins picks the wrong one.
        text = "{} {} {}".format(cluster.lead.title, cluster.lead.title, cluster.combined_text)
        best, best_score = None, 0.0
        for weight, pattern, explanation in IMPACT_RULES:
            score = weight * len(pattern.findall(text))
            if score > best_score:
                best, best_score = explanation, score
        if best is None:
            return DEFAULT_IMPACT
        sources = len({a.source.lower() for a in cluster.articles})
        if sources >= 3:
            return "{} Covered by {} separate outlets in the last day.".format(best, sources)
        return best

    def summarise_cluster(self, cluster: Cluster, section: str) -> Story:
        what_happened = self._what_happened(cluster)
        return Story(
            headline=cluster.title,
            what_happened=what_happened,
            simply_explained=self._simply_explained(cluster, what_happened),
            why_it_matters=self._why_it_matters(cluster),
            sources=cluster.sources,
            published=max(a.published for a in cluster.articles),
            score=cluster.score,
            section=section,
            funding=cluster.score_breakdown.get("funding"),
        )


PROMPT = """You are writing one entry in a personal morning news briefing.

Work ONLY from the source material below. Do not add facts, numbers, names or context
that are not present in it. If the material is too thin to explain the story, say so
plainly in the field rather than filling the gap.

The reader is intelligent but not a specialist in AI, technology, finance or geopolitics.
Explain technical terms in plain English without being patronising. British English.

what_happened:    2-3 sentences, factual, from the source material only.
simply_explained: 2-3 sentences decoding any jargon or background needed to follow it.
                  Say what a thing actually IS and does, not just that it exists.
                  If nothing needs decoding, say the story is already plain.
why_it_matters:   1-2 sentences on the significance. No speculation beyond the material.

Section: {section}
Headline: {headline}
Outlets covering it: {sources}

Source material:
{material}
"""

# Structured outputs guarantee valid JSON back, which removes the "model returned
# something unparseable" failure mode entirely.
RESPONSE_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "what_happened": {"type": "string"},
            "simply_explained": {"type": "string"},
            "why_it_matters": {"type": "string"},
        },
        "required": ["what_happened", "simply_explained", "why_it_matters"],
        "additionalProperties": False,
    },
}


class LLMSummariser(Summariser):
    """Pluggable model backend. Falls back to extractive per-story on any failure."""

    name = "llm"

    def __init__(self):
        self.fallback = ExtractiveSummariser()
        self.calls = 0
        self._client = None
        self._use_refusal_fallback = True
        self.name = "llm:{}:{}".format(config.llm_provider, config.llm_model)

    def _material(self, cluster: Cluster) -> str:
        chunks = []
        for article in cluster.sources[:5]:
            body = article.full_text or (article.summary if article.summary_usable else "")
            chunks.append("[{}] {}\n{}".format(article.source, article.title, body))
        return "\n\n".join(chunks)[:6000]

    def _call(self, prompt: str) -> Optional[dict]:
        if config.llm_provider == "anthropic":
            return self._call_anthropic(prompt)
        return self._call_openai_compatible(prompt)

    def _call_anthropic(self, prompt: str) -> Optional[dict]:
        import anthropic

        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=config.llm_api_key or None, timeout=config.llm_timeout
            )

        request = {
            "model": config.llm_model,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
            # "low" effort suits summarisation: the work is faithful compression, not
            # hard reasoning, and effort is the main cost dial.
            "output_config": {"format": RESPONSE_SCHEMA, "effort": config.llm_effort},
        }

        if self._use_refusal_fallback:
            try:
                response = self._client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
                )
            except anthropic.BadRequestError as exc:
                # Only a rejected request shape means the beta is unavailable here.
                # Auth, rate-limit and server errors must propagate, not be masked.
                log.warning("Refusal fallback unavailable (%s); continuing without it", exc)
                self._use_refusal_fallback = False
                response = self._client.messages.create(**request)
        else:
            response = self._client.messages.create(**request)

        if getattr(response, "stop_reason", None) == "refusal":
            log.warning("Model declined to summarise a story; using extractive instead")
            return None

        text = next((b.text for b in response.content if b.type == "text"), "")
        return json.loads(text) if text else None

    def _call_openai_compatible(self, prompt: str) -> Optional[dict]:
        """Any OpenAI-shaped endpoint: Groq, OpenRouter, a local Ollama, etc."""
        import requests

        base = config.llm_base_url.rstrip("/") or "https://api.openai.com/v1"
        response = requests.post(
            "{}/chat/completions".format(base),
            headers={
                "Authorization": "Bearer {}".format(config.llm_api_key),
                "Content-Type": "application/json",
            },
            json={
                "model": config.llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 900,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            timeout=config.llm_timeout,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", raw, re.S)
        return json.loads(match.group(0)) if match else None

    def summarise_cluster(self, cluster: Cluster, section: str) -> Story:
        story = self.fallback.summarise_cluster(cluster, section)
        if self.calls >= config.llm_max_stories:
            return story
        try:
            self.calls += 1
            data = self._call(
                PROMPT.format(
                    section=section,
                    headline=cluster.title,
                    sources=", ".join(a.source for a in cluster.sources[:5]),
                    material=self._material(cluster),
                )
            )
            if data and all(k in data for k in
                            ("what_happened", "simply_explained", "why_it_matters")):
                story.what_happened = data["what_happened"].strip()
                story.simply_explained = data["simply_explained"].strip()
                story.why_it_matters = data["why_it_matters"].strip()
        except Exception as exc:
            log.warning("LLM summarisation failed (%s) — using extractive for: %s",
                        exc, cluster.title[:60])
        return story


def get_summariser() -> Summariser:
    if config.summariser == "llm":
        if not config.llm_api_key and config.llm_provider != "openai_compatible":
            log.warning("SUMMARISER=llm but no LLM_API_KEY set — falling back to extractive")
            return ExtractiveSummariser()
        return LLMSummariser()
    return ExtractiveSummariser()
