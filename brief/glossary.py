"""Plain-English definitions used by the no-LLM summariser.

These are hand-written definitions of recurring jargon, not generated text — which
is why the extractive mode can explain terms without inventing anything about the
story itself. Add your own entries freely.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

GLOSSARY: Dict[str, str] = {
    # AI
    "large language model": "a text-prediction system trained on huge amounts of writing; ChatGPT and Claude are examples",
    "llm": "large language model — a text-prediction system trained on huge amounts of writing",
    "foundation model": "a big general-purpose AI model that other products are built on top of",
    "open-weight": "the model's trained parameters are downloadable, so anyone can run it themselves",
    "open weights": "the model's trained parameters are downloadable, so anyone can run it themselves",
    "inference": "the cost and act of actually running an AI model to answer a request (as opposed to training it)",
    "training run": "the one-off, very expensive process of building a model from data",
    "fine-tuning": "taking an existing model and cheaply specialising it on extra data",
    "benchmark": "a standard test used to compare AI models; results are easy to game, so treat them loosely",
    "multimodal": "handles more than text — images, audio or video too",
    "ai agent": "an AI system given tools and permission to take actions, not just answer questions",
    "context window": "how much text a model can consider at once",
    "hallucination": "when a model states something confidently that is simply false",
    "gpu": "the specialised chip used to train and run AI models; supply of these is the industry's main bottleneck",
    "tpu": "Google's own AI chip, an alternative to Nvidia GPUs",
    "compute": "raw processing capacity — the chips, data centres and power behind AI",
    "distillation": "training a small cheap model to imitate a big expensive one",
    "rag": "retrieval-augmented generation — letting a model look things up before answering",
    "alignment": "research into making AI systems behave as intended",
    "training data": "the text, images or code a model learned from — increasingly the subject of copyright fights",
    "copyright infringement": "using someone's work without permission; the central legal question in most AI-and-publishers disputes",
    "copyright": "the right to control copying of a work — the core of the disputes between publishers and AI companies over training data",
    "open source": "the code is public and anyone can inspect, use or modify it",
    "orbit": "reaching orbit means going fast enough sideways to keep missing the planet — the hard part of a launch, not the height",
    "class action": "one lawsuit brought on behalf of a large group of people with the same complaint",
    "antitrust probe": "a competition regulator formally investigating whether a company is abusing its market position",
    "guardrails": "the restrictions built into a model to stop it doing things its makers do not want it to do",
    "jailbreak": "a prompt that talks a model past its own restrictions",
    "api": "the interface other companies' software uses to call a service programmatically",
    "chain of thought": "a model working through a problem in steps before answering",

    # Chips / hardware
    "foundry": "a factory that manufactures chips designed by other companies (TSMC is the biggest)",
    "fab": "a chip fabrication plant",
    "node": "the manufacturing generation of a chip — smaller numbers mean newer, denser, more efficient",
    "euv": "extreme ultraviolet lithography — the machinery needed to make the most advanced chips, made only by ASML",
    "export controls": "government rules restricting which technology can be sold to which countries",

    # Security
    "zero-day": "a security flaw being exploited before the vendor has a fix available",
    "0-day": "a security flaw being exploited before the vendor has a fix available",
    "rce": "remote code execution — the worst class of flaw, letting an attacker run their own code on someone else's machine",
    "remote code execution": "the worst class of flaw: an attacker can run their own code on someone else's machine",
    "patch": "the fix a vendor ships for a security flaw; the risk window is the gap before everyone installs it",
    "ransomware": "malware that encrypts a victim's files and demands payment",
    "supply chain attack": "breaking into a supplier so you reach all of its customers at once",
    "phishing": "tricking someone into handing over credentials via a fake message or site",
    "cve": "the public catalogue number given to a specific software vulnerability",

    # Money / startups
    "pre-seed": "the earliest outside money a startup takes, usually before it has real revenue",
    "seed": "early funding to build the product and find first customers",
    "series a": "the first big institutional round, typically once a product has traction",
    "series b": "growth funding to scale a business that already works",
    "valuation": "the price investors put on the whole company at the moment they invest",
    "oversubscribed": "more investors wanted in than there was room for",
    "down round": "raising money at a lower valuation than last time — usually a bad sign",
    "runway": "how many months of cash the company has left",
    "dilution": "existing owners' stakes shrinking because new shares were issued",
    "term sheet": "the non-binding outline of an investment's terms",
    "ipo": "initial public offering — a company listing its shares on a stock market",

    # Geopolitics / trade
    "sanctions": "legal restrictions on trading with, or moving money to, a country, company or person",
    "tariff": "a tax on imported goods, used to protect domestic industry or apply pressure",
    "ceasefire": "an agreement to stop fighting, usually temporary and often fragile",
    "coalition government": "several parties governing together because no single one won a majority",
    "no-confidence": "a parliamentary vote that can remove a government or leader",
    "referendum": "a direct public vote on a single question",
    "antitrust": "competition law — rules stopping companies abusing dominant market positions",
    "quantitative easing": "a central bank creating money to buy assets and lower borrowing costs",
    "central bank": "the institution that sets a country's interest rates and manages its currency",
    "sovereign wealth fund": "a state-owned investment fund, often funded by oil or trade surpluses",
    "nato": "a 32-country military alliance in which an attack on one is treated as an attack on all",
    "eu ai act": "the European Union's law regulating AI by risk category, the first of its kind",
    "gdpr": "the EU's data-protection law, which carries fines of up to 4% of global revenue",
}

_GLOSSARY_PATTERNS: List[Tuple[str, str, "re.Pattern"]] = [
    (term, meaning, re.compile(r"\b{}s?\b".format(re.escape(term)), re.I))
    for term, meaning in GLOSSARY.items()
]


def find_terms(text: str, limit: int = 3) -> List[Tuple[str, str]]:
    """Return (term, plain-English meaning) pairs present in the text, longest first."""
    hits = [(term, meaning) for term, meaning, pattern in _GLOSSARY_PATTERNS if pattern.search(text)]
    hits.sort(key=lambda pair: -len(pair[0]))
    # Drop terms that are contained in a longer matched term (llm vs large language model).
    kept: List[Tuple[str, str]] = []
    for term, meaning in hits:
        if any(term in existing.lower() for existing, _ in kept):
            continue
        kept.append((term, meaning))
        if len(kept) >= limit:
            break
    return kept
