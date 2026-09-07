# Morning News Brief

A personalised morning news briefing that builds itself and arrives by email. It currently
covers AI developments, global politics, world technology and startup funding, and runs
every morning without me touching it. No paid news APIs or data subscriptions.

## Why I built it

There is no shortage of morning briefings. I did not build this because there was no way
to get one. I built it because I wanted control over exactly what information I receive.

Right now I care about AI, global politics, technology and startup funding. Those
interests will change, and when they do I can change the topics, sources, weighting,
filters and structure. A newsletter is somebody else's editorial judgement about what a
general audience wants. This is mine, and I can rewrite it. The point is personalisation
and control, not that I think I can build a better general news service than professional
news organisations.

## What it does

- collects recent stories from RSS feeds and Google News RSS
- groups different articles covering the same event
- scores and ranks stories using transparent rules
- filters out stories I have already received, using a rolling 7-day memory
- organises what is left into four sections
- extracts company, amount, stage and investors from funding announcements
- generates a clean HTML briefing
- emails it to me automatically every morning

## How does it decide what matters?

It does not understand importance the way a human editor would. It uses a transparent
rule-based score built from proxies: how many independent publications are covering the
same event, how much weight I have given each source, relevance to my chosen topics,
recency, and penalties for gossip-style framing. These are stand-ins for importance, not
judgement.

I chose rules over a model for the first version because they are free, transparent, easy
for me to adjust, and because when something ranks strangely I can open the file and see
exactly why. A model would rank better. This one I can debug.

Each signal is explained in [Technical Details](#ranking-system).

## 7-day memory

This is the change I am happiest with, because it came from using the thing rather than
planning it.

I got my Saturday brief, then my Sunday brief, and it was largely the same news. The cause
was my own ranking: a big story keeps accumulating coverage, so the corroboration signal
scored yesterday's story even higher today. Deduplicating within a single morning did
nothing about it, because each morning started from a blank slate.

So the system now keeps a rolling 7-day record of stories that were actually sent, and
suppresses sufficiently similar ones from later briefs. It is still text similarity rather
than any understanding of whether a story has genuinely developed, which is a real limit
and one I have written up honestly below.

## How it works

```
RSS feeds + Google News RSS
        |
        v
   Collect stories
        |
        v
   Group same-event coverage
        |
        v
   Detect funding + classify into sections
        |
        v
   Score and rank
        |
        v
   Check 7-day memory
        |
        v
   Select top stories
        |
        v
   Fetch article text
        |
        v
   Write up and format
        |
        v
   Email
        |
        v
   Save memory
```

Two orderings are deliberate. The memory check runs after scoring, so a suppressed story is
replaced by the next best one rather than leaving a gap. And article text is fetched only
for the stories that will actually appear, which is a few dozen requests rather than one
per article collected.

## The brief

**🤖 AI Developments.** New models, research, company announcements, regulation, and the
chip and data centre stories underneath all of it.

**🌍 Global Politics.** Elections, conflicts, diplomacy, sanctions, trade disputes and
changes of government, weighted towards international consequences.

**💻 World Technology.** Everything technical not already covered as AI: semiconductors,
cybersecurity, space, robotics, big tech regulation.

**🚀 Startup Funding Radar.** Recently announced rounds with the details extracted where
the source states them, UK and Europe first.

A story appears in one section only, which is enforced rather than hoped for.

## Built with

Python · RSS · Google News RSS · GitHub Actions · HTML email

I built and iterated on this with Claude Code, Anthropic's agentic coding tool, using it to
write, debug and refine the implementation while I defined the workflow, product logic,
constraints and the changes made after actually using it.

## Why these choices?

**RSS instead of a news API.** I wanted V1 to cost nothing to run. RSS is free and flexible,
though less complete and less structured than a paid API, and some major publications no
longer offer a usable free feed.

**GitHub Actions instead of running it on my Mac.** The brief needs to arrive without me
running anything manually or leaving my laptop switched on overnight.

**Email instead of a dashboard.** I already check email every morning. Building another
destination I have to remember to visit would defeat part of the purpose.

**Rules instead of an LLM for ranking.** The first version needed to stay free and
explainable. Rule-based ranking is imperfect, but I can see and change exactly why
something was selected.

**Extraction instead of generated text.** In a news brief, inventing detail is the one
unacceptable failure, so the default writes nothing it cannot quote. The cost of that
honesty is explained under [Summarisation](#summarisation-and-plain-english-explanations).

---

# Technical Details

## Sources and discovery

**Problem.** A fixed list of publishers only tells me what those publishers covered.
Searching broadly instead returns a lot of noise.

**Decision.** Both, treated differently. 45 hand-picked feeds are the anchors, each with a
trust weight I assigned. 20 Google News RSS searches provide discovery. Anchors are
preferred when choosing which version of a story to lead with, and discovery-only stories
score lower unless several outlets corroborate them.

**Trade-off.** More sources means more noise, so this only works with filtering: 26 blocked
publishers (mostly stock-tipping sites that flood technology searches) and 75 headline
patterns for listicles, SEO spam and press-release filler. That list is maintenance I have
signed myself up for.

Reuters, Bloomberg and the FT no longer offer usable free feeds, so the mix leans towards
the BBC, the Guardian, Al Jazeera, DW, NYT, Politico Europe and similar. Google News RSS is
not a documented API and could change without warning.

## Deduplication

**Problem.** Five articles about one event should be one item in my brief, not five. Google
News links are redirects rather than real URLs, so matching on the link is useless.

**Decision.** Group on text similarity. `deduplication.py` takes the words from each
headline (counted double) plus the opening 320 characters of the summary, weights them by
how rare each word is across everything collected that morning so names and places matter
more than filler, and compares stories by how much of the smaller one is contained in the
larger. That containment measure lets a short headline match a wordy one about the same
event. A second pass merges groups that turned out to be the same thing, and an inverted
index avoids comparing every story against every other one. Default threshold 0.30.

**Trade-off.** Two outlets can describe one event with almost no shared vocabulary. "German
company launches rocket" and "Isar Aerospace reaches orbit" are the same story and this
will not always catch it. Lowering the threshold merges more but starts collapsing
genuinely different stories together.

The group size also feeds ranking, since the number of distinct publications in a group is
the corroboration signal.

## Ranking system

All in `ranking.py`. Every story gets a score and the highest scoring ones go in.

**How many separate publications are covering it.** The strongest signal available and the
heaviest weighted. If eleven independent outlets wrote about the same event within a day,
that is decent evidence something happened. It is a proxy for editorial consensus without
needing an editor. Counted per distinct publication, capped at six so one enormous story
cannot dominate everything.

**How much I trust the source.** Every feed carries a weight I assigned by hand. The BBC and
Ars Technica score above an aggregator I barely know. This is my judgement baked into a
number and it is as arbitrary as that sounds.

**Whether an established feed carried it at all.** Stories found only through Google News
search score lower, because discovery results are noisier. That reduction shrinks as more
outlets pile in, so a real story none of my feeds happened to carry can still get through.

**Relevance to the section.** Each section has a weighted keyword list. Matching is on whole
words, which sounds like a detail but wasn't: an early version matched substrings and filed
a story about a tick-borne virus under AI, because "agi" appears inside the word "against".

**Recency.** Full marks under six hours old, tailing off to a floor at the edge of the
lookback window. Weaker here than in most feeds, deliberately. I would rather have
yesterday evening's important story than this morning's trivial one.

**Penalties for gossip framing.** Points subtracted for headline patterns that usually
signal filler: "slams", "hits back", "row over", "reportedly", "here's what to expect".
This targets how a story is written up rather than what it is about.

Funding stories additionally get a boost for anything UK or European, including rounds
denominated in pounds or euros even when the headline never names a country.

**Limitations.** It has no idea what any of these stories mean. Corroboration rewards widely
covered stories, which is not the same as important ones, and it systematically underrates
things that matter but that nobody has picked up yet. The keyword lists are mine and they
are incomplete.

## 7-day memory implementation

`history.py` stores every story that goes out, with the date and the set of significant
words from its headline, in `state/seen.json`. Each morning, after scoring and before the
top stories are chosen, every candidate is compared against that record. The comparison is
the overlap between the two sets of headline words divided by the size of the smaller set;
0.6 or above counts as already sent and is dropped. Entries older than seven days are
discarded. Clusters with fewer than three significant words are skipped rather than guessed
at.

Stories are recorded only once the email has actually gone out, so a failed run or a local
preview does not consume news I never received.

The part that took the most thought was where to keep it. GitHub wipes the machine after
every run, so a file written during the run disappears with it. The workflow commits
`state/seen.json` back into the repository, which is why there is a daily commit from
`github-actions[bot]`. Slightly odd looking, but it is free, it survives, and I can open the
file and read what it thinks it has sent me.

**What it does not do.** It compares headline words and has no concept of a story
developing. A genuine new development written up in different enough words will come
through, and that is a side effect of vocabulary rather than the system recognising
anything. A real development described in familiar words will be suppressed. `HISTORY_DAYS`
and `HISTORY_THRESHOLD` are both adjustable and both are guesses that seem to work.

## Classification

**Problem.** A funding round for an AI company is legitimately AI news and funding news.
Putting it in both wastes a slot and makes the brief repetitive.

**Decision.** Group first, then assign each group to exactly one section. Funding claims a
story first; everything else goes to the section with the strongest keyword evidence. A
story with no real evidence for any section is dropped rather than filed somewhere by
default.

**Trade-off.** Occasionally a story lands somewhere I would not have put it. Making the
sections mutually exclusive is what stops that becoming a wider problem.

## Failure handling

**Problem.** One dead feed should not cost me the whole briefing.

**Decision.** Every feed is fetched independently and a failure is logged and skipped.
Article fetches fail silently and fall back to whatever the feed gave. A corrupt memory file
starts a fresh one instead of stopping. Malformed entries are skipped without taking the
feed down with them. Quiet mornings, mostly weekends, widen the window from 26 to 48 hours
rather than sending an empty brief.

**Trade-off.** Degrading quietly means a feed could be broken for weeks without me noticing.
The run log reports how many articles each source returned, which is the only real defence.

Two environment problems worth recording, both now handled in code. Python installed from
python.org ships with no certificate store, so TLS to Gmail fails with
`CERTIFICATE_VERIFY_FAILED`; the code uses certifi's bundle rather than the system store.
And values pasted into a `.env` file or a GitHub secret often carry a trailing newline,
which turns a hostname into something DNS cannot resolve, so every setting is trimmed when
read.

## Article fetching

Google News RSS gives you a headline and a redirect link, and its summary field is a list of
links to other outlets rather than a summary. The redirect sits behind a consent wall that
cannot be resolved from a server, which I confirmed before giving up on it.

What Google News does give you is the publisher's domain. So when a story has no real
article URL, `article_fetcher.py` fetches that publisher's front page and looks for a link
whose text closely matches the headline. Correct matches scored above 0.8 in testing and
wrong ones below 0.45, so the threshold sits at 0.62. Anything fetched is then checked for
the headline's distinctive words before use, which catches the case where a link resolved to
a section index and the "summary" would have been the publication's own marketing copy.

On a typical run this gets real article text for around three quarters of the stories. The
rest fall back to showing how several outlets headlined the story.

## Summarisation and plain-English explanations

Part of why I wanted my own briefing is that I want to follow AI and technology properly
without pretending I already understand every term. So each story is laid out as three
things: what happened, what that means in plain terms, and why it might matter.

**What happened** is assembled from sentences the publisher actually wrote, taken from the
fetched article text. Nothing there is generated, which means nothing there can be invented.

**Simply explained** and **why it matters** are placeholders. Deliberate ones, but I want to
be clear that is what they are.

"Simply explained" is currently a glossary lookup against 68 definitions I wrote by hand
(inference, foundation model, zero-day, Series A, export controls and so on). There is an
obvious problem with that: I can only write a definition for a term I already understand
well enough to define. So the glossary explains things I already know and stays quiet about
the ones I don't, which is precisely backwards from what I wanted. It proves the slot works.
It does not do the job.

"Why it matters" has the same shape of problem. Ten weighted rules spot the category of
event in the text (a court case, an acquisition, a funding round, a security incident, a
chip supply story) and each category has a sentence explaining why that kind of event tends
to have consequences. It can tell you why acquisitions matter in general. It cannot tell you
why this acquisition matters, because it has no idea what it is looking at. It also picks
the wrong category from time to time.

Both become genuinely useful the moment a language model is connected, for the same reason:
a model works from the story actually in front of it rather than from a list I wrote in
advance. It can explain a term I have never heard of, and say what this particular
development means instead of what its category usually means.

So the structure is the part I think is right, and two thirds of the implementation is
scaffolding holding the shape open until something better goes in it. The summariser sits
behind an interface with two implementations and switching is a config change rather than a
rewrite. I built and tested the model path, measured the cost, and left it off so the
default stays free. I would rather it be visibly limited than quietly invent explanations it
cannot produce.

## Startup funding extraction

I wanted a lightweight way of noticing companies that have just raised money, weighted
towards the UK and Europe. The round itself is interesting, but the more useful part is
discovery: a seed round is often the first time you hear a company's name at all.

`funding.py` detects announcements by requiring the funding verb, the money and the absence
of negative context to co-occur in a single sentence. That last part matters: without it,
"£1.7bn cost-cutting plan" and "$25m settlement" both read as venture rounds. The company
name is read backwards from the funding verb, stopping at the first word that cannot be part
of a name.

Everything extracted is taken word for word from the source. Anything the source does not
state shows as "not stated in source" rather than being filled in. This is not coverage of
the funding market: without a paid database it only sees rounds announced in the feeds I am
reading, so expect gaps, worst outside the UK, Europe and the US.

## Architecture

```
main.py                   pipeline orchestration and CLI
brief/
  config.py               every setting, all overridable by environment variable
  feeds.py                feed list, search queries, keywords, noise and block lists
  models.py               Article, Cluster, Story, FundingItem, Brief
  news_collector.py       parallel fetching and normalisation
  deduplication.py        grouping articles about the same event
  classification.py       section assignment
  ranking.py              scoring
  history.py              7-day record of what has already been sent
  funding.py              funding detection and field extraction
  article_fetcher.py      pulls article text for stories that make the brief
  summariser.py           Summariser interface, extractive and LLM implementations
  glossary.py             68 hand-written plain English definitions
  formatter.py            HTML and plain text rendering
  email_sender.py         SMTP delivery
```

Each stage takes a list and returns a list, so any stage can be swapped or tested on its own.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

```bash
python main.py --no-email --open   # build without sending
python main.py --dry-run           # ranked headlines only, useful when tuning
python main.py --test-email        # check email settings on their own
python main.py                     # the real thing
```

## Email configuration

Gmail needs an App Password, not your account password. Turn on 2-Step Verification, then
create one at https://myaccount.google.com/apppasswords and put it in `.env`:

```
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-character-app-password
EMAIL_TO=you@gmail.com
```

## GitHub Actions

1. Push the repository to GitHub.
2. Settings, then Secrets and variables, then Actions. Add `SMTP_HOST`, `SMTP_PORT`,
   `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`.
3. Actions tab, Morning Brief, Run workflow, to test it immediately.

```yaml
- cron: "30 6 * * *"   # 06:30 UTC daily
```

GitHub cron is always UTC and does not follow British Summer Time, so 06:30 UTC is 07:30 in
London in summer and 06:30 in winter. The job needs `contents: write` permission because it
commits the memory file back after a successful run.

A private repository gets 2,000 free minutes a month and this uses about 60. Scheduled runs
can be delayed by several minutes when GitHub is busy, and GitHub disables scheduled
workflows in repositories with no activity for 60 days, so if the brief stops arriving for
no obvious reason, push any commit to re-enable it.

## Configuration

Everything is an environment variable. Full list in `.env.example`.

| Setting | Default | What it does |
|---|---|---|
| `LOOKBACK_HOURS` | 26 | how far back to look |
| `FALLBACK_LOOKBACK_HOURS` | 48 | widened window when a morning is too quiet |
| `MIN_ARTICLES` | 120 | below this, the wider window is used |
| `MAX_STORIES_AI` | 6 | stories per section (same pattern for the others) |
| `MAX_EXTRA_HEADLINES` | 4 | link-only headlines under each section |
| `SUPPRESS_SEEN` | true | false to allow repeats from recent briefs |
| `HISTORY_DAYS` | 7 | how long a story counts as already sent |
| `HISTORY_THRESHOLD` | 0.6 | headline overlap needed to count as the same story |
| `DEDUPE_THRESHOLD` | 0.30 | lower merges more aggressively |
| `MIN_SECTION_EVIDENCE` | 2.5 | keyword evidence needed to file a story at all |
| `CORROBORATION_WEIGHT` | 2.2 | how much "many outlets covered it" counts |
| `RECENCY_WEIGHT` | 2.0 | how much newness counts |
| `KEYWORD_WEIGHT` | 1.6 | how much topic relevance counts |
| `PREFERRED_REGIONS` | uk, europe, ... | region boost, mainly for funding |
| `FETCH_ARTICLES` | true | false to skip page fetching, much thinner summaries |
| `GOOGLE_NEWS_LOCALE` | GB:en | `US:en` for US weighting |

To change what is collected rather than how much, edit `feeds.py`: `ANCHOR_FEEDS` for
publishers, `DISCOVERY_QUERIES` for the searches, `SECTION_KEYWORDS` for what belongs where,
`NOISE_PATTERNS` and `BLOCKED_SOURCES` for what to throw away. Add your own jargon to
`GLOSSARY` in `glossary.py` and it appears in "simply explained" whenever it comes up.

## Optional LLM summariser

```
SUMMARISER=llm
LLM_PROVIDER=anthropic
LLM_MODEL=claude-opus-5
LLM_API_KEY=sk-ant-...
LLM_EFFORT=low
LLM_MAX_STORIES=20
```

Then `pip install anthropic`. It is not in `requirements.txt` because the default needs no
model at all.

One request per story carrying the headline, the outlets covering it and the fetched article
text. Structured outputs guarantee valid JSON back, which removes the "model replied with
prose instead" failure mode. Effort is low because summarising is faithful compression
rather than hard reasoning. Refusal fallback is enabled, since a brief covering wars and
cyberattacks will occasionally trip a safety classifier. Every story falls back to its
extractive version if the call fails, so a model outage degrades the brief rather than
breaking it.

Measured on a real run of 24 stories: about 13,400 input tokens and 5,500 output tokens a
day.

| Model | Per day | Per month |
|---|---|---|
| Claude Opus 5 | ~$0.21 | ~$6 |
| Claude Sonnet 5 | ~$0.08 | ~$2.50 |
| Claude Haiku 4.5 | ~$0.04 | ~$1.25 |

Thinking tokens are billed as output, so budget roughly double. `LLM_MAX_STORIES` is a hard
ceiling on calls per run and is the real protection against a runaway bill.

Free options exist with caveats. A local Ollama is free and private but needs your own
machine awake at 7am, and is impractical on GitHub Actions where every run would download
the weights again. Free API tiers cost nothing but are rate limited, can change, and usually
train on your inputs. Both work through `LLM_PROVIDER=openai_compatible` with `LLM_BASE_URL`.

## Known limitations

**Ranking is a proxy.** Corroboration is the best free signal for importance and it is still
only a signal. Important stories nobody has picked up yet get underrated by design.

**"Simply explained" is the weakest part.** Without a model it is a glossary lookup and a
category label, not a real explanation.

**Deduplication misses some pairs.** Two outlets can describe one event with no shared
vocabulary.

**The memory cannot tell development from repetition.** It compares headline words.

**Funding coverage has real gaps.** No paid database means it only sees announcements that
reached the feeds being read.

**Some major publications have no usable free feed,** so the source mix is skewed.

**"Last 24 hours" is approximate.** Feeds report times inconsistently and Google News
`when:1d` is its own approximation.

**Google News RSS is undocumented.** Free and stable in practice, but not a supported API.

**Article fetching is best effort.** About three quarters of stories on a typical run, and
roughly one in twenty of those pulls text from a related but not identical article.

## Project structure

```
morning-brief/
  main.py
  brief/
    config.py  feeds.py  models.py  news_collector.py  deduplication.py
    classification.py  ranking.py  history.py  funding.py  article_fetcher.py
    summariser.py  glossary.py  formatter.py  email_sender.py
  state/
    seen.json               record of what has already been sent
  requirements.txt
  .env.example
  .github/workflows/morning-brief.yml
```
