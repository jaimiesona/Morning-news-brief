"""Detect funding announcements and pull structured fields out of the text.

Strict rule: every field is extracted verbatim from the headline/summary. If the
source does not state a value, the field stays None and the brief shows "not stated".
Nothing here guesses.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from .config import config
from .models import Cluster, FundingItem

log = logging.getLogger(__name__)

SIGNAL_RE = re.compile(
    r"\b(raises?|raised|raising|secures?|secured|closes?|closed|lands?|landed|nets?|"
    r"bags?|snags?|picks up|pulls in|banks|funding round|venture round|"
    r"backed by|led by|seed round|investment round)\b",
    re.I,
)
STAGE_RE = re.compile(
    r"\b(pre[\s-]?seed|seed(?:\s+(?:round|funding|extension))?|series\s+[a-j]\b|"
    r"growth round|bridge round|angel round|debt facility|grant)\b",
    re.I,
)
AMOUNT_RE = re.compile(
    r"([£$€]|\bUSD\b|\bEUR\b|\bGBP\b)\s?(\d{1,4}(?:[.,]\d{1,3})?)\s*"
    r"(billion|bn\b|b\b|million|mn\b|m\b|k\b)?",
    re.I,
)
INVESTOR_RE = re.compile(
    r"\b(?:led by|co-led by|backed by|with participation from|from investors?)\s+"
    r"([A-Z][\w&.'’\-]*(?:\s+[A-Z0-9][\w&.'’\-]*){0,3}"
    r"(?:(?:,|\s+and\s+)\s*[A-Z][\w&.'’\-]*(?:\s+[A-Z0-9][\w&.'’\-]*){0,3}){0,4})"
)
# "London-based Foo", "UK startup Foo", "Berlin-headquartered Foo"
LOCATION_PREFIX_RE = re.compile(
    r"\b([A-Z][a-zA-Z.\- ]{2,24})[- ](?:based|headquartered)\b"
)

KNOWN_PLACES = [
    "london", "manchester", "cambridge", "oxford", "edinburgh", "bristol", "leeds",
    "dublin", "paris", "berlin", "munich", "hamburg", "amsterdam", "rotterdam",
    "stockholm", "copenhagen", "helsinki", "oslo", "zurich", "geneva", "madrid",
    "barcelona", "milan", "rome", "lisbon", "warsaw", "prague", "vienna", "brussels",
    "tallinn", "vilnius", "athens", "istanbul", "tel aviv", "new york", "san francisco",
    "boston", "seattle", "austin", "toronto", "singapore", "bangalore", "tokyo",
    "sydney", "dubai", "united kingdom", "uk", "france", "germany", "spain", "italy",
    "netherlands", "sweden", "denmark", "norway", "finland", "ireland", "switzerland",
    "poland", "portugal", "estonia", "israel", "india", "china", "japan", "canada",
    "australia", "united states", "us", "usa",
]

MULTIPLIERS = {
    "billion": 1_000_000_000, "bn": 1_000_000_000, "b": 1_000_000_000,
    "million": 1_000_000, "mn": 1_000_000, "m": 1_000_000,
    "k": 1_000,
}
# Static conversion rates, used only to sort rounds by rough size.
FX_TO_USD = {"£": 1.27, "gbp": 1.27, "€": 1.08, "eur": 1.08, "$": 1.0, "usd": 1.0}

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# Money in these contexts is not a funding round. Without this guard, "£1.7bn
# cost-cutting plan" and "$25m settlement" both read as venture rounds.
NEGATIVE_CONTEXT_RE = re.compile(
    r"\b(job cuts?|cut \d|cutting|layoffs?|redundanc\w+|settlement|damages|fine[sd]?|"
    r"penalt\w+|lawsuit|sues?|revenue|profits?|losses|writedown|write-off|buyback|"
    r"bailout|bankrupt\w*|market cap|share price|dividend|budget|spending review|"
    r"contract worth|order worth|deal worth|acquisition of|acquires?|bought for)\b",
    re.I,
)


def _candidate_sentences(cluster) -> List[str]:
    """Title first, then summary sentences — the round is usually stated in one place."""
    sentences = [cluster.lead.title]
    for article in cluster.articles[:6]:
        sentences.append(article.title)
        if article.full_text:
            sentences.extend(s.strip() for s in _SENTENCE_RE.split(article.full_text))
        if article.summary and article.summary_usable:
            sentences.extend(s.strip() for s in _SENTENCE_RE.split(article.summary))
    return [s for s in sentences if s]


def find_funding_sentence(cluster) -> Optional[str]:
    """The one sentence that states the round, or None if no sentence does.

    Requiring the verb, the money and the absence of negative context to co-occur in
    a single sentence is what stops unrelated numbers elsewhere in the story from
    being read as a funding amount.
    """
    for sentence in _candidate_sentences(cluster):
        if NEGATIVE_CONTEXT_RE.search(sentence):
            continue
        if not SIGNAL_RE.search(sentence):
            continue
        if AMOUNT_RE.search(sentence) or STAGE_RE.search(sentence):
            return sentence
    return None


def parse_amount(text: str) -> Tuple[Optional[str], float]:
    match = AMOUNT_RE.search(text)
    if not match:
        return None, 0.0
    symbol, number, unit = match.group(1), match.group(2), (match.group(3) or "").lower().strip()
    display = "{}{}{}".format(symbol.upper() if len(symbol) > 1 else symbol, number,
                              {"bn": "bn", "b": "bn", "billion": "bn",
                               "mn": "m", "m": "m", "million": "m", "k": "k"}.get(unit, ""))
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return display, 0.0
    value *= MULTIPLIERS.get(unit, 1)
    return display, value * FX_TO_USD.get(symbol.lower(), 1.0)


def parse_stage(text: str) -> Optional[str]:
    match = STAGE_RE.search(text)
    if not match:
        return None
    return " ".join(word.capitalize() for word in match.group(1).split())


def parse_investors(text: str) -> List[str]:
    names: List[str] = []
    for match in INVESTOR_RE.finditer(text):
        chunk = match.group(1)
        for name in re.split(r",|\band\b", chunk):
            name = name.strip(" .;:")
            if 2 < len(name) < 45 and name.lower() not in ("the", "a"):
                names.append(name)
    seen, unique = set(), []
    for name in names:
        if name.lower() not in seen:
            seen.add(name.lower())
            unique.append(name)
    return unique[:5]


def parse_location(text: str) -> Optional[str]:
    match = LOCATION_PREFIX_RE.search(text)
    if match:
        return match.group(1).strip()
    lowered = text.lower()
    for place in KNOWN_PLACES:
        if re.search(r"\b{}\b".format(re.escape(place)), lowered):
            return place.title() if len(place) > 3 else place.upper()
    return None


# Words that mark the edge of a company name when scanning backwards from the verb.
_NAME_BOUNDARY = {
    "startup", "start-up", "startups", "scaleup", "scale-up", "company", "companies",
    "firm", "maker", "developer", "provider", "platform", "business", "group",
    "unicorn", "venture", "app", "specialist", "the", "this", "a", "an", "its",
    "uk", "us", "eu", "european", "british", "german", "french", "dutch", "nordic",
    "irish", "spanish", "italian", "swiss", "swedish", "indian", "israeli",
    "fintech", "biotech", "healthtech", "insurtech", "deeptech", "climate", "energy",
    "defence", "defense", "space", "quantum", "robotics", "cyber", "cybersecurity",
}
_TRAILING_FILLER = {
    "just", "now", "today", "finally", "officially", "reportedly", "said", "has",
    "have", "is", "are", "will", "to", "and", "after", "as", "in",
} | _NAME_BOUNDARY


def parse_company(title: str) -> Optional[str]:
    """Read the company name backwards from the funding verb.

    Headlines put the name immediately before the verb ("London-based Acme raises"),
    so we walk left from the verb and stop at the first word that cannot be part of
    a name — a descriptor like "startup", a determiner, or any punctuation.
    """
    match = SIGNAL_RE.search(title)
    if not match:
        return None
    head = title[: match.start()]
    head = re.sub(r"^(exclusive|breaking|just in)\s*[:\-–]\s*", "", head, flags=re.I)
    head = LOCATION_PREFIX_RE.sub("", head)

    words = head.split()
    while words and words[-1].lower().strip(".,;:") in _TRAILING_FILLER:
        words.pop()

    name: List[str] = []
    for word in reversed(words):
        bare = word.strip(".,;:'\u2019()[]")
        if not bare:
            break
        # Punctuation or a possessive ends the name ("Kuwait's Dawraty" -> "Dawraty").
        if "'" in word or "\u2019" in word or word.endswith((",", ":", ";", ".")):
            break
        lowered = bare.lower()
        if lowered in _NAME_BOUNDARY and not (bare.isupper() and len(name) < 2):
            break
        if not (bare[0].isupper() or bare.isdigit()):
            break
        name.insert(0, bare)
        if len(name) >= 3:
            break

    if not name:
        return None
    candidate = " ".join(name)
    if candidate.lower() in KNOWN_PLACES or len(candidate) < 2:
        return None
    return candidate


def parse_description(cluster: Cluster) -> Optional[str]:
    """First sentence of the source summary that isn't just the headline again."""
    for article in cluster.articles:
        body = article.full_text or (article.summary if article.summary_usable else "")
        if not body:
            continue
        for sentence in _SENTENCE_RE.split(body):
            sentence = sentence.strip()
            if 40 <= len(sentence) <= 320:
                return sentence
    return None


def extract(cluster: Cluster) -> Optional[FundingItem]:
    sentence = find_funding_sentence(cluster)
    if not sentence:
        return None

    # Fields are read from the funding sentence, with the headline as backup for
    # details a summary sentence often omits (stage, investors).
    scope = "{} {}".format(sentence, cluster.lead.title)

    amount, amount_usd = parse_amount(sentence)
    if amount is None:
        amount, amount_usd = parse_amount(scope)
    stage = parse_stage(scope)
    if not amount and not stage:
        return None

    lowered = " {} ".format(cluster.combined_text.lower())
    return FundingItem(
        company=parse_company(cluster.lead.title) or parse_company(sentence),
        description=parse_description(cluster),
        location=parse_location(scope),
        amount=amount,
        amount_usd=amount_usd,
        stage=stage,
        investors=parse_investors(scope),
        is_preferred_region=any(region in lowered for region in config.preferred_regions),
    )


def find_funding(clusters: List[Cluster]) -> List[Cluster]:
    """Tag clusters that are funding announcements; returns them in place."""
    found = []
    for cluster in clusters:
        item = extract(cluster)
        if item:
            cluster.score_breakdown["funding"] = item
            found.append(cluster)
    log.info("Funding radar matched %d stories", len(found))
    return found
