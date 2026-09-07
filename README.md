# Morning News Brief

A daily news briefing that collects from free RSS feeds, groups duplicate coverage of
the same event, ranks stories by importance, writes them up in four sections and emails
you a clean HTML brief. No paid APIs, no paid data services, no LLM required.

Four sections: **Latest AI developments**, **Global politics**, **World technology**,
**Startup funding radar**. Each story gets a headline, what happened, a plain-English
explanation, why it matters, and links to every source that covered it.

---

## How it works

```
feeds.py            what to read: ~45 anchor RSS feeds + 20 Google News RSS queries
   ↓
news_collector.py   fetch all of them in parallel, normalise, drop noise and stale items
   ↓
deduplication.py    cluster articles that describe the same event
   ↓
funding.py          find funding announcements, extract company/amount/stage/investors
   ↓
classification.py   file each cluster into exactly one section
   ↓
ranking.py          score by corroboration, source quality, keywords, recency
   ↓
article_fetcher.py  fetch the opening of the page — only for stories that made the cut
   ↓
summariser.py       write the three paragraphs (extractive by default, LLM optional)
   ↓
formatter.py        render HTML + plain text
   ↓
email_sender.py     send over SMTP
```

`main.py` runs that pipeline. `config.py` holds every setting, all overridable by
environment variable. `models.py` holds the data structures passed between stages.
`glossary.py` holds hand-written plain-English definitions of recurring jargon.

### The design decisions worth knowing

**Discovery vs anchors.** Google News RSS search finds stories nobody's dedicated feed
would surface. Anchor feeds (BBC, Guardian, Ars Technica, TechCrunch, Politico EU,
EU-Startups…) are trusted, so their articles carry more weight and are preferred when
choosing which version of a story to lead with.

**Deduplication without URLs.** Google News links are opaque redirects, so URL matching
can't spot the same story from two outlets. Clustering runs on text instead: headline
tokens (weighted double) plus the opening of the summary, weighted by inverse document
frequency so rare words — names, places, companies — decide matches. Similarity is
normalised by the smaller of the two token sets so a terse headline still matches a
wordy one, and a second pass merges clusters that turned out to be the same event.

**Ranking by importance, not recency.** The strongest free signal is corroboration: if
40 outlets covered something in 24 hours it matters more than a single blog post.
Score combines distinct-source count, best source weight, section keyword density and a
recency curve, then subtracts a penalty for gossip framing ("slams", "row over",
"reportedly").

**One brief, one story — across days as well.** Ranking rewards corroboration, and a
big story keeps accumulating coverage, so without a memory the same subject wins every
morning under a slightly different headline. `history.py` keeps a record of what has
already been sent (`state/seen.json`, 7 days by default) and filters those out. On GitHub
Actions the workflow commits that file back to the repository, because a runner's disk is
wiped after every run. Set `SUPPRESS_SEEN=false` to turn it off, or `HISTORY_DAYS` to
change the window.

**One story, one section.** Funding announcements are claimed first by the funding
radar; everything else is filed by keyword evidence into a single best-matching section.
A story can't appear twice.

**Nothing is invented.** In the default extractive mode the brief only ever reuses the
publishers' own sentences. Jargon explanations come from a hand-written glossary, and
"why it matters" comes from rules keyed to the *category* of event detected in the text
— neither asserts new facts about the story. Where a source said nothing, the brief says
"not stated in source" rather than guessing.

---

## Honest limitations

Things in the original spec that RSS alone cannot fully deliver, and what happens instead:

**"Simply explained" is the weak point without an LLM.** Extractive mode can quote the
source and define jargon, but it cannot genuinely re-explain a complex story in fresh
plain English — that requires a language model. The `Summariser` interface exists exactly
for this: set `SUMMARISER=llm` and it swaps in without touching anything else. See
[Adding an LLM summariser](#adding-an-llm-summariser) for costs (~$6/month on Opus 5,
measured) and the genuinely-free options.

**Google News gives headlines, not text.** Its RSS `description` field is a list of links
to other outlets, not a summary. So for a story that only Google News found, the brief has
nothing to quote and falls back to showing how three different outlets headlined it. Its
links are also opaque redirects — they work fine in a browser, but you'll see
`news.google.com/rss/articles/…` in the URL bar before it forwards you.

**Reuters, Bloomberg, FT, WSJ, The Economist have no usable free RSS.** They are either
withdrawn, paywalled, or headline-only. The anchor list uses BBC, Guardian, Al Jazeera,
DW, France 24, NPR, Politico EU and UN News instead, which is a genuinely different
editorial mix — mostly European and Anglophone.

**Deduplication is good, not perfect.** Two outlets writing about the same event with no
shared vocabulary ("German company launches rocket" vs "Isar Aerospace reaches orbit")
can survive as separate stories. Lower `DEDUPE_THRESHOLD` to merge more aggressively at
the risk of collapsing genuinely different stories together.

**Funding coverage has real gaps.** Many rounds only ever appear in a paywalled outlet or
a press release that no free feed carries. There is no free equivalent of Crunchbase. The
radar finds what appeared in the feeds it reads, and extracts only fields the text
actually states — expect "not stated in source" often, particularly for location and
investors.

**"Last 24 hours" is approximate.** Feeds report publication times inconsistently, and
Google News `when:1d` is its own approximation. Default window is 26 hours. On quiet
mornings (weekends, holidays) many anchor feeds have nothing new, so the window
automatically widens to 48 hours rather than sending you an empty brief.

**Google News RSS is undocumented.** It is free and stable in practice, but it is not a
supported API. It can rate-limit or change shape without notice. The brief degrades
rather than breaks: every feed is fetched independently and a failure is logged and
skipped.

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Build a brief without sending anything:

```bash
python main.py --no-email --open
```

See just the ranked headlines, to check the filters are behaving:

```bash
python main.py --dry-run
```

### Email

Edit `.env`. For Gmail you need an **App Password**: turn on 2-step verification, then
create one at <https://myaccount.google.com/apppasswords>. Your normal Google password
will not work, and the old "less secure apps" setting no longer exists.

```
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-character-app-password
EMAIL_TO=you@gmail.com
```

Then:

```bash
python main.py
```

### Automating it with GitHub Actions

1. Push this repo to GitHub.
2. Settings → Secrets and variables → Actions → **Secrets**, add:
   `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`.
3. Actions tab → *Morning Brief* → **Run workflow** to test it immediately.

The schedule lives in `.github/workflows/morning-brief.yml`:

```yaml
- cron: "30 6 * * *"   # 06:30 UTC every day
```

Cron in GitHub Actions is **always UTC**, with no daylight-saving handling — 06:30 UTC is
07:30 in London during BST and 06:30 in winter. If you want a fixed local time
year-round, run two schedules and let the unwanted one exit, or just accept the hour
drift. Scheduled runs can also be delayed by several minutes when GitHub is busy.

Free-tier note: Actions minutes are unlimited on public repos; private repos get 2,000
minutes a month. A run takes about two minutes, so roughly 60 minutes a month.

GitHub disables scheduled workflows in repos with no activity for 60 days. If the brief
stops arriving, push any commit to re-enable it.

---

## Tuning

Everything is an environment variable — see `.env.example` for the full list.

| Setting | Does what |
|---|---|
| `LOOKBACK_HOURS` | how far back to look (default 26) |
| `MAX_STORIES_AI` etc. | stories per section |
| `MAX_EXTRA_HEADLINES` | link-only headlines under each section |
| `DEDUPE_THRESHOLD` | lower merges more aggressively (default 0.30) |
| `MIN_SECTION_EVIDENCE` | how much keyword evidence a story needs to be filed at all |
| `PREFERRED_REGIONS` | region boost, mainly for the funding radar |
| `SUPPRESS_SEEN` | `false` to allow stories repeated from recent briefs |
| `HISTORY_DAYS` | how long a story counts as already-sent (default 7) |
| `FETCH_ARTICLES` | set `false` to skip page fetching (faster, much thinner summaries) |
| `MAX_ARTICLE_FETCHES` | cap on pages fetched per run (default 30) |
| `CORROBORATION_WEIGHT` | how much "many outlets covered it" counts |
| `GOOGLE_NEWS_LOCALE` | `GB:en` for UK weighting, `US:en` for US |

To change *what* is collected rather than how much, edit `feeds.py`: `ANCHOR_FEEDS` for
publishers, `DISCOVERY_QUERIES` for Google News searches, `SECTION_KEYWORDS` for what
belongs in which section, `NOISE_PATTERNS` and `BLOCKED_SOURCES` for what to throw away.

Add your own jargon definitions to `GLOSSARY` in `glossary.py` — they show up in
"Simply explained" whenever the term appears in a story.

---

## Adding an LLM summariser

`summariser.py` defines a `Summariser` interface with two implementations. Switching is
a config change, not a rewrite:

```
SUMMARISER=llm
LLM_PROVIDER=anthropic
LLM_MODEL=claude-opus-5
LLM_API_KEY=sk-ant-...
LLM_EFFORT=low
LLM_MAX_STORIES=20
```

Then `pip install anthropic`. It is not in `requirements.txt` because the default mode
needs no model at all.

### What actually happens per story

One HTTP request each, to `POST /v1/messages`, carrying the headline, the outlets that
covered it, and the article text the fetcher pulled. The response comes back as JSON with
the three fields the brief renders.

Three implementation choices worth knowing:

- **Structured outputs** (`output_config.format` with a JSON schema) guarantee valid JSON
  back. Without it you are regex-scraping prose and handling the day the model wraps its
  answer in a sentence.
- **`effort: low`** — effort is the main cost dial. Summarisation is faithful compression
  rather than hard reasoning, so it does not repay a high setting. Raise it if the
  explanations feel shallow.
- **Refusal fallback** — safety classifiers occasionally decline a request, which for a
  brief covering wars and cyberattacks is a live possibility. The server-side `fallbacks`
  parameter reroutes those automatically. If your account does not have that beta, the
  code notices once and carries on without it.

Every story falls back to its extractive summary if the call fails, the model declines, or
the JSON is unusable — a model outage degrades the brief rather than breaking it.

### What it costs

Measured from a real run: 24 stories, ~13,400 input tokens and ~5,500 output tokens a day.

| Model | `LLM_MODEL` | Per day | Per month |
|---|---|---|---|
| Claude Opus 5 | `claude-opus-5` | ~$0.21 | **~$6** |
| Claude Sonnet 5 | `claude-sonnet-5` | ~$0.08 | ~$2.50 |
| Claude Haiku 4.5 | `claude-haiku-4-5` | ~$0.04 | ~$1.25 |

Two caveats. Thinking tokens are billed as output, so budget roughly double the figures
above at `effort: low` and more above it. And `LLM_MAX_STORIES` is a hard ceiling on calls
per run — the real protection against a runaway bill.

### Genuinely free alternatives

- **Local Ollama** — free and private, but needs your own machine awake at 7am. Not
  practical in GitHub Actions, which would download several GB of weights on every run.
  Set `LLM_PROVIDER=openai_compatible` and `LLM_BASE_URL=http://localhost:11434/v1`.
- **Free API tiers** (Google AI Studio, Groq) — cost nothing today, but are rate-limited,
  can change, and usually train on your inputs. Fine for public news text. Same
  `openai_compatible` setting with that provider's base URL.

To add a different backend, subclass `Summariser`, implement `summarise_cluster`, and
return it from `get_summariser()`.

## Project layout

```
morning-brief/
├── main.py                  pipeline orchestration + CLI
├── brief/
│   ├── config.py            all settings, env-overridable
│   ├── feeds.py             feed catalogue, queries, keywords, noise lists
│   ├── models.py            Article, Cluster, Story, FundingItem, Brief
│   ├── news_collector.py    parallel fetching and normalisation
│   ├── article_fetcher.py   fetches article text for stories that make the brief
│   ├── history.py           remembers what previous briefs contained
│   ├── deduplication.py     clustering same-event articles
│   ├── classification.py    section assignment
│   ├── ranking.py           importance scoring
│   ├── funding.py           funding detection and field extraction
│   ├── summariser.py        Summariser interface + extractive and LLM backends
│   ├── glossary.py          plain-English jargon definitions
│   ├── formatter.py         HTML and plain-text rendering
│   └── email_sender.py      SMTP delivery
├── requirements.txt
├── .env.example
└── .github/workflows/morning-brief.yml
```
