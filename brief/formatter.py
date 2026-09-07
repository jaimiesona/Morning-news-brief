"""Render the brief as an HTML email (with a plain-text alternative).

Email clients strip <style> blocks and ignore most modern CSS, so everything here
is inline styles on simple block elements.
"""

from __future__ import annotations

import html
from typing import List

from .config import config
from .feeds import SECTIONS
from .models import Article, Brief, Story

INK = "#16181d"
MUTED = "#5b6472"
LINE = "#e3e6ea"
ACCENT = "#1f5fbf"
BG = "#f5f6f8"
CARD = "#ffffff"

SECTION_ICON = {"ai": "◆", "politics": "▲", "technology": "●", "funding": "£"}


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def _label(text: str) -> str:
    return (
        '<div style="font:600 11px/1.4 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'letter-spacing:.08em;text-transform:uppercase;color:{muted};margin:14px 0 4px;">{t}</div>'
    ).format(muted=MUTED, t=_esc(text))


def _body(text: str, allow_html: bool = False) -> str:
    content = text if allow_html else _esc(text)
    return (
        '<div style="font:400 15px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:{ink};margin:0;">{c}</div>'
    ).format(ink=INK, c=content)


def _source_links(sources: List[Article]) -> str:
    links = [
        '<a href="{url}" style="color:{accent};text-decoration:none;">{name}</a>'.format(
            url=html.escape(a.best_url, quote=True), accent=ACCENT, name=_esc(a.source)
        )
        for a in sources[:6]
    ]
    return (
        '<div style="font:400 13px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:{muted};margin-top:12px;padding-top:10px;border-top:1px solid {line};">'
        'Sources: {links}</div>'
    ).format(muted=MUTED, line=LINE, links=" &middot; ".join(links))


def _funding_facts(story: Story) -> str:
    item = story.funding
    if not item:
        return ""
    rows = [
        ("Company", item.company),
        ("What it does", item.description),
        ("Location", item.location),
        ("Amount", item.amount),
        ("Stage", item.stage),
        ("Investors", ", ".join(item.investors) if item.investors else None),
    ]
    cells = []
    for key, value in rows:
        shown = _esc(value) if value else '<span style="color:#9aa3af;">not stated in source</span>'
        cells.append(
            '<tr>'
            '<td style="padding:3px 12px 3px 0;font:600 13px/1.5 -apple-system,Segoe UI,Roboto,'
            'Helvetica,Arial,sans-serif;color:{muted};white-space:nowrap;vertical-align:top;">{k}</td>'
            '<td style="padding:3px 0;font:400 14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,'
            'Arial,sans-serif;color:{ink};">{v}</td></tr>'.format(muted=MUTED, ink=INK, k=_esc(key), v=shown)
        )
    return (
        '<table cellpadding="0" cellspacing="0" border="0" style="width:100%;margin:10px 0 0;'
        'border-collapse:collapse;">{}</table>'.format("".join(cells))
    )


def _story_html(story: Story, index: int) -> str:
    parts = [
        '<div style="background:{card};border:1px solid {line};border-radius:10px;'
        'padding:18px 20px;margin:0 0 14px;">'.format(card=CARD, line=LINE),
        '<div style="font:700 18px/1.35 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:{ink};margin:0 0 2px;"><a href="{url}" style="color:{ink};text-decoration:none;">'
        '{n}. {headline}</a></div>'.format(
            ink=INK,
            url=html.escape(story.sources[0].best_url, quote=True) if story.sources else "#",
            n=index,
            headline=_esc(story.headline),
        ),
    ]
    if story.funding:
        parts.append(_funding_facts(story))
    parts.append(_label("What happened"))
    parts.append(_body(story.what_happened))
    parts.append(_label("Simply explained"))
    parts.append(_body(story.simply_explained, allow_html=True))
    parts.append(_label("Why it matters"))
    parts.append(_body(story.why_it_matters))
    parts.append(_source_links(story.sources))
    parts.append("</div>")
    return "".join(parts)


def _extras_html(extras: List[Article]) -> str:
    if not extras:
        return ""
    items = [
        '<li style="margin:0 0 6px;"><a href="{url}" style="color:{accent};text-decoration:none;">'
        '{title}</a> <span style="color:{muted};">— {source}</span></li>'.format(
            url=html.escape(a.best_url, quote=True), accent=ACCENT, muted=MUTED,
            title=_esc(a.title), source=_esc(a.source)
        )
        for a in extras
    ]
    return (
        '<div style="margin:0 0 26px;padding:14px 20px;background:{card};border:1px dashed {line};'
        'border-radius:10px;"><div style="font:600 11px/1.4 -apple-system,Segoe UI,Roboto,Helvetica,'
        'Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:{muted};margin:0 0 8px;">'
        'Also worth a glance</div><ul style="margin:0;padding-left:18px;font:400 14px/1.5 -apple-system,'
        'Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:{ink};">{items}</ul></div>'
    ).format(card=CARD, line=LINE, muted=MUTED, ink=INK, items="".join(items))


def _section_header(key: str, count: int) -> str:
    return (
        '<div style="margin:30px 0 14px;padding-bottom:8px;border-bottom:2px solid {ink};">'
        '<span style="font:700 20px/1.3 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:{ink};">{icon} {title}</span>'
        '<span style="float:right;font:400 13px/1.9 -apple-system,Segoe UI,Roboto,Helvetica,Arial,'
        'sans-serif;color:{muted};">{count} stories</span></div>'
    ).format(ink=INK, muted=MUTED, icon=SECTION_ICON.get(key, "•"), title=SECTIONS[key], count=count)


def render_html(brief: Brief) -> str:
    date_line = brief.generated_at.strftime("%A %d %B %Y")
    body = [
        '<div style="margin:0;padding:0;background:{bg};">'.format(bg=BG),
        '<div style="max-width:660px;margin:0 auto;padding:26px 16px 40px;">',
        '<div style="font:700 26px/1.25 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:{ink};margin:0 0 2px;">Morning Intelligence Brief</div>'.format(ink=INK),
        '<div style="font:400 14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:{muted};margin:0 0 6px;">{date} &middot; last {hours} hours</div>'.format(
            muted=MUTED, date=date_line, hours=config.lookback_hours),
    ]

    total = sum(len(v) for v in brief.sections.values())
    if not total:
        body.append(_body("No stories cleared the filters this morning. That usually means the "
                          "feeds were slow rather than that the world was quiet."))

    for key in config.enabled_sections:
        stories = brief.sections.get(key, [])
        extras = brief.extra_headlines.get(key, [])
        if not stories and not extras:
            continue
        body.append(_section_header(key, len(stories)))
        for i, story in enumerate(stories, start=1):
            body.append(_story_html(story, i))
        body.append(_extras_html(extras))

    stats = brief.stats
    body.append(
        '<div style="margin-top:26px;padding-top:14px;border-top:1px solid {line};font:400 12px/1.6 '
        '-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:{muted};">'
        'Assembled from {feeds} feeds &middot; {articles} articles &middot; {clusters} distinct stories '
        '&middot; {enriched} with fetched article text &middot; summariser: {summariser}.<br>'
        'Everything above is extracted from the linked sources. Nothing is invented; where a source '
        'said nothing, the brief says so.</div>'.format(
            line=LINE, muted=MUTED,
            feeds=stats.get("feeds", "?"), articles=stats.get("articles", "?"),
            clusters=stats.get("clusters", "?"), enriched=stats.get("enriched", 0),
            summariser=_esc(brief.summariser_name))
    )
    body.append("</div></div>")

    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Morning Intelligence Brief &mdash; {date}</title></head>"
        '<body style="margin:0;padding:0;background:{bg};">{body}</body></html>'
    ).format(date=date_line, bg=BG, body="".join(body))


def render_text(brief: Brief) -> str:
    lines = [
        "MORNING INTELLIGENCE BRIEF",
        brief.generated_at.strftime("%A %d %B %Y"),
        "=" * 60,
        "",
    ]
    for key in config.enabled_sections:
        stories = brief.sections.get(key, [])
        if not stories:
            continue
        lines += [SECTIONS[key].upper(), "-" * 60, ""]
        for i, story in enumerate(stories, start=1):
            lines.append("{}. {}".format(i, story.headline))
            if story.funding:
                f = story.funding
                lines.append("   {} | {} | {} | {}".format(
                    f.company or "company not stated", f.amount or "amount not stated",
                    f.stage or "stage not stated", f.location or "location not stated"))
            lines += [
                "   WHAT HAPPENED: " + story.what_happened,
                "   SIMPLY: " + story.simply_explained.replace("<strong>", "").replace("</strong>", ""),
                "   WHY IT MATTERS: " + story.why_it_matters,
                "   SOURCES: " + " | ".join("{} {}".format(a.source, a.best_url) for a in story.sources[:4]),
                "",
            ]
        for extra in brief.extra_headlines.get(key, []):
            lines.append("   - {} ({}) {}".format(extra.title, extra.source, extra.best_url))
        lines.append("")
    return "\n".join(lines)
