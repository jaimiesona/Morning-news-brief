#!/usr/bin/env python3
"""Morning Intelligence Brief — entry point.

  python main.py              collect, build, save, email (per config)
  python main.py --no-email   build and save the HTML only
  python main.py --open       also open the result in a browser
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import webbrowser
from datetime import datetime, timezone

from brief.config import config
from brief.feeds import SECTIONS, all_feeds
from brief import (article_fetcher, classification, deduplication, email_sender,
                   formatter, funding, news_collector, ranking)
from brief.history import History
from brief.models import Brief
from brief.summariser import get_summariser

log = logging.getLogger("morning-brief")


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_brief() -> Brief:
    feeds = all_feeds()
    articles = news_collector.collect(feeds)
    if not articles:
        log.error("No articles collected — every feed failed or nothing was published.")

    clusters = deduplication.cluster_articles(articles)

    funding_clusters = funding.find_funding(clusters) if "funding" in config.enabled_sections else []
    funding_ids = {id(c) for c in funding_clusters}

    buckets = classification.classify(clusters, funding_ids)
    history = History()
    summariser = get_summariser()

    selected, extras = {}, {}
    for key in config.enabled_sections:
        ranked = history.filter_new(ranking.rank(buckets.get(key, []), key))
        limit = config.max_stories_for(key)
        selected[key] = ranked[:limit]
        extras[key] = [c.lead for c in ranked[limit:limit + config.max_extra_headlines]]
        log.info("Section %-11s -> %d stories, %d extra headlines",
                 key, len(selected[key]), len(extras[key]))

    # Fetch article text only for the stories that made the cut — a few dozen
    # requests rather than one per article collected.
    enriched = 0
    if config.fetch_articles:
        enriched = article_fetcher.enrich([c for clusters in selected.values() for c in clusters])

    sections = {key: summariser.summarise(clusters, key) for key, clusters in selected.items()}
    brief_history = history

    brief = Brief(
        generated_at=datetime.now(timezone.utc),
        sections=sections,
        extra_headlines=extras,
        stats={"feeds": len(feeds), "articles": len(articles), "clusters": len(clusters),
               "enriched": enriched},
        summariser_name=summariser.name,
    )
    # Only remember stories once they are actually going out.
    for clusters in selected.values():
        brief_history.record(clusters)
    brief.history = brief_history
    return brief


def test_email() -> int:
    """Check the email settings on their own, before involving the news pipeline."""
    problems = config.validate_email()
    if problems:
        log.error("Email is not configured yet: %s", "; ".join(problems))
        log.error("Fill these in in your .env file, then run this again.")
        return 1

    log.info("Sending test email to %s via %s:%s as %s",
             ", ".join(config.email_to), config.smtp_host, config.smtp_port, config.smtp_user)
    html = (
        "<div style=\"font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;color:#16181d\">"
        "<h2>Morning Brief — test email</h2>"
        "<p>If you are reading this, your email settings work and the real brief "
        "will arrive the same way.</p></div>"
    )
    text = "Morning Brief test email. If you are reading this, your email settings work."
    if email_sender.send("Morning Brief — test email", html, text):
        log.info("Sent. Check your inbox (and the spam folder).")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and send the morning intelligence brief.")
    parser.add_argument("--no-email", action="store_true", help="skip sending, just build")
    parser.add_argument("--open", action="store_true", help="open the saved HTML in a browser")
    parser.add_argument("--dry-run", action="store_true", help="collect and print counts only")
    parser.add_argument("--test-email", action="store_true",
                        help="send a short test email and exit, without building a brief")
    args = parser.parse_args()

    setup_logging()
    started = datetime.now(timezone.utc)

    if args.test_email:
        return test_email()

    try:
        brief = build_brief()
    except Exception as exc:
        log.exception("Brief generation failed: %s", exc)
        return 1

    total = sum(len(v) for v in brief.sections.values())
    log.info("Built %d stories in %.1fs", total, (datetime.now(timezone.utc) - started).total_seconds())

    if args.dry_run:
        for key, stories in brief.sections.items():
            print("\n== {} ==".format(SECTIONS[key]))
            for story in stories:
                print("  [{:.2f}] {}".format(story.score, story.headline))
        return 0

    html_body = formatter.render_html(brief)
    text_body = formatter.render_text(brief)

    path = None
    if config.save_html:
        os.makedirs(config.output_dir, exist_ok=True)
        path = os.path.join(config.output_dir, "brief-{}.html".format(started.strftime("%Y-%m-%d")))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(html_body)
        log.info("Saved %s", path)
        if args.open:
            webbrowser.open("file://" + os.path.abspath(path))

    if total == 0:
        log.warning("Brief is empty — not sending.")
        return 0

    delivered = False
    if config.send_email and not args.no_email:
        subject = "{} \u2014 {}".format(config.email_subject_prefix, started.strftime("%a %d %b"))
        if not email_sender.send(subject, html_body, text_body):
            return 1
        delivered = True

    # Only a brief that actually reached you counts as seen. A preview run must not
    # consume today's news and leave tomorrow's brief with nothing to report.
    history = getattr(brief, "history", None)
    if history is not None and delivered:
        history.save()
    elif history is not None:
        log.info("Nothing sent, so the story history was left unchanged.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
