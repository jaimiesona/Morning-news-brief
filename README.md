# Morning News Brief

A personalised morning news briefing that builds itself and arrives by email. Every
morning it reads a few dozen news feeds, works out which stories look most significant,
groups the coverage, writes each one up, and sends me a single email covering four
areas: AI developments, global politics, world technology, and startup funding.

It runs on free RSS feeds and GitHub Actions. There is no paid news API behind it and,
in the default setup, no language model either. Where that limits what it can do, I have
tried to say so plainly rather than paper over it.

---

## Why I built this

There is no shortage of morning briefings. Newsletters, apps, the news sites themselves.
I did not build this because there was no way to get one.

I built it because I wanted a briefing shaped around the specific things I care about
right now. At the moment that means AI developments, global politics, world technology,
and startup funding, with a bias towards the UK and Europe on the funding side.

The real advantage is not that my version is better than a professionally edited
newsletter. It clearly isn't. The advantage is that my interests are going to change,
and when they do I can change the topics, the sources, how they are weighted, and how the
whole thing is structured. A newsletter I subscribe to is somebody else's editorial
judgement about what a general audience wants. This is mine, and I can rewrite it.

So the goal was personalisation and control, not building another news aggregator.

## Why RSS

I wanted the first version to cost nothing to run. Not "cheap", actually nothing. That
ruled out paid news APIs and data subscriptions from the start.

RSS is a good fit for that constraint. Most publications still publish a feed of what
they have just put out, it is free, it is lightweight, and reading thirty of them takes
a couple of seconds. On top of that I use Google News RSS, which lets me search for
topics rather than subscribe to publishers, so the brief can pick up a story from an
outlet I have never heard of.

The honest trade-off is that RSS is worse than a paid API in almost every way except
price. Feeds carry headlines and short summaries rather than structured data. Some major
publications (Reuters, Bloomberg, the FT) no longer offer a usable free feed at all, so
my source mix leans towards the BBC, the Guardian, Al Jazeera, DW, Politico Europe and
similar. Publication timestamps are inconsistent. Google News RSS is not a documented
API and could change without warning.

None of that makes RSS the right answer in general. It made it the right answer for a
free personal V1.

## How stories get selected

This is the part I want to be most careful about, because it would be easy to describe
it in a way that makes it sound cleverer than it is.

The program does not understand the news. It cannot tell that a coup matters more than a
product launch. What it has is a rule based scoring system that uses a handful of
measurable signals as a rough stand in for importance. Every story gets a score, and the
highest scoring ones go in the brief.

The signals, all of which live in `ranking.py`:

**How many separate publications are covering it.** This is the strongest signal I have
and it carries the most weight. If eleven independent outlets wrote about the same event
within a day, that is decent evidence something happened. It is a proxy for editorial
consensus without needing an editor. Counted per distinct publication, capped at six so
one enormous story cannot completely dominate.

**How much I trust the source.** Every feed has a weight I assigned by hand. The BBC and
Ars Technica score higher than an aggregator I barely know. This is my judgement baked
into a number, and it is as arbitrary as that sounds.

**Whether an established feed carried it at all.** Stories found only through Google News
search get a reduced score, because discovery results are noisier. That reduction shrinks
as more outlets pile in, so a real story that none of my chosen feeds happened to carry
can still get through.

**Relevance to the section.** Each of the four sections has a keyword list with weights.
A story that keeps saying "semiconductor" and "export controls" scores well for
technology. Matching is on whole words, which sounds like a detail but wasn't: an early
version matched substrings and put a story about a tick borne virus in the AI section,
because "agi" appears inside the word "against".

**How recent it is.** Full marks for anything under six hours old, tailing off towards
the edge of the lookback window. Recency is a weaker signal here than in most feeds,
which is deliberate. I would rather have yesterday evening's important story than this
morning's trivial one.

**Penalties for gossip framing.** Points are subtracted for headline patterns that
usually signal filler rather than a development: "slams", "hits back", "row over",
"reportedly", "here's what to expect", and so on. This targets how a story is written up
rather than what it is about.

Funding stories additionally get a boost for anything that looks UK or European,
including rounds denominated in pounds or euros even when the headline never names a
country.

The limitations are real. It has no idea what any of these stories mean. Corroboration
rewards stories that are widely covered, which is not the same as stories that are
important, and it systematically underrates things that matter but that nobody has picked
up yet. The keyword lists are mine and they are incomplete. A better version of this
would use a language model to rank, and the code is structured so that could be added,
but I wanted to see how far transparent rules could get first. Partly because it is free,
partly because when the ordering looks wrong I can open the file and see exactly why.

## Why deduplicate

Open any news aggregator and you get five headlines about the same event from five
publications, taking up five slots.

I care about the event. The fact that six outlets covered it is useful information, but
it should be one item in my brief that says "six outlets covered this", not six items.

So the program groups articles that look like they describe the same underlying story and
presents each group as a single development, keeping the links to every source underneath
it. The group also feeds the ranking, since the number of distinct publications in a
group is the corroboration signal.

Doing this without a paid API is harder than it sounds, mainly because Google News links
are redirects rather than real URLs, so matching on the link is useless. The grouping in
`deduplication.py` therefore works on the text. It takes the words from each headline
(counted double) plus the opening of the summary, weights them by how rare each word is
across everything collected that morning so that names and places matter more than filler,
and compares stories by how much of the smaller one is contained in the larger. That last
choice lets a short headline match a wordy one about the same event. A second pass then
merges groups that turned out to be the same thing, and an inverted index keeps it from
comparing every story against every other one.

It is not perfect and it fails in a specific way: two outlets can describe the same event
with almost no shared vocabulary. "German company launches rocket" and "Isar Aerospace
reaches orbit" are the same story and this system will not always spot it.

## Why a 7 day memory

This one came directly from using the thing.

I got my Saturday brief. Then I got my Sunday brief, and it was largely the same news.
Not identical headlines, but the same events: the same OpenAI story, the same model
launch, worded slightly differently.

The cause was my own ranking. Corroboration rewards stories covered by many outlets, and
a big story keeps accumulating coverage for days, so on day two it scores even higher
than it did on day one. Deduplicating within a single morning does nothing about this,
because each morning started from a blank slate. The program had no idea what it had
already sent me.

So it now keeps a record. `history.py` stores every story that goes out, with the date and
the set of significant words from its headline, in `state/seen.json`. Each morning, before
the top stories are chosen, every candidate is compared against that record. The
comparison is the overlap between the two sets of headline words divided by the size of
the smaller set, and anything scoring 0.6 or above counts as already sent and is dropped.
Entries older than seven days are discarded. Stories are only recorded once the email has
actually gone out, so a failed run doesn't cause tomorrow to skip news I never received.

The part that took the most thought was where to keep it. GitHub wipes the machine after
every run, so a file written during the run disappears with it. The workflow now commits
`state/seen.json` back into the repository, which is why there is a daily commit from
`github-actions[bot]` in the history. It is a slightly odd looking solution but it is
free, it survives, and I can open the file and read what it thinks it has sent me.

I want to be precise about what this does not do. It compares headline words. It has no
concept of a story developing. If a genuine new development in an ongoing story is written
up with different enough wording it will come through, and that is a side effect of
vocabulary rather than the system recognising that something new happened. Equally, a
real development described in familiar words will be suppressed. Seven days and a
threshold of 0.6 are both adjustable and both are guesses that seem to work.

The reason for all of it is simple. I want the brief to tell me what is new, not to tell
me again what I read yesterday.

## Why plain English explanations

Part of why I wanted my own briefing is that I want to follow AI and technology properly
without pretending I already understand every term in them. I am comfortable reading about
this stuff. I am not an expert in it, and a lot of coverage assumes I am.

So each story is laid out as three things:

1. What happened
2. What that means in plain terms
3. Why it might matter

I need to be straight about how well the current version does this.

The default setup uses no language model, and the reason is that it stays free. What it
does instead is extractive. "What happened" is assembled from sentences the publisher
actually wrote, taken from the article text the program fetches for the stories that make
the brief. Nothing there is generated, which means nothing there can be invented.

"Simply explained" is a glossary lookup. I have hand written definitions for 68 recurring
terms (inference, foundation model, zero-day, Series A, export controls, and so on) and
if any appear in the story the brief explains them. When none appear it says so instead
of padding.

"Why it matters" comes from ten weighted rules that spot the category of event in the
text: a court case, an acquisition, a funding round, a security incident, a chip supply
story, and so on. Each has a short explanation of why that kind of event generally has
consequences.

That last one is the weakest part and I would rather flag it than dress it up. It tells
you why acquisitions matter in general, not why this acquisition matters. It is a
category label with a sentence attached, and occasionally it picks the wrong category.

Genuine contextual rewriting needs a language model. There is no clever free workaround
and I would rather have honest extraction than invented explanation. So the summariser is
behind an interface with two implementations, and switching to a model is a config change
rather than a rewrite. I measured what that would cost before deciding not to do it by
default. Details are further down.

## Why a startup funding section

I wanted a lightweight way of noticing companies that have just raised money, with a
bias towards the UK and Europe.

The funding itself is interesting, but the more useful part is what it surfaces. A seed
round is often the first time you hear a company's name at all, and a run of rounds in
one area says something about where investors think things are going. It is a way of
finding out what exists.

Where possible the brief pulls out the company, what it does, the location, the amount,
the stage, the investors and the source link.

I am not claiming coverage of the funding market. Without something like Crunchbase this
radar sees exactly one thing: funding announcements that happened to appear in the feeds
I am reading. Plenty of rounds are announced somewhere I am not looking, or only in a
paywalled outlet. Expect gaps, and expect them to be worst outside the UK, Europe and the
US.

Everything it does extract is taken word for word from the source text. When a source
does not state the location or the investors, the brief says "not stated in source"
rather than filling it in. I would rather have a field that admits it is empty than a
field I cannot trust.

## Why GitHub Actions

The brief is only useful if it turns up without me doing anything. Running a Python
script by hand at seven in the morning is not a system, it is a chore, and leaving my Mac
switched on overnight to run a scheduler is worse.

GitHub Actions runs it on a schedule on their machines, whether or not my laptop is even
open. For a job this small it also stays inside the free allowance: private repositories
get 2,000 minutes a month and this uses about 60. It also gives me a log of every run,
which turned out to matter more than I expected while debugging.

## Why email

To reduce friction to nearly zero.

I already open my email in the morning. If I had built this as a dashboard, I would have
to remember to go and look at it, and a thing that is supposed to save me time would have
become another thing to check. So the brief comes to me, in the place I am already going
to be.

---

## How it works

```
RSS feeds + Google News RSS
        |
        v
   Collect stories        (65 sources in parallel, last ~26 hours)
        |
        v
   Group same-event coverage
        |
        v
   Detect funding announcements
        |
        v
   Classify into sections
        |
        v
   Score and rank
        |
        v
   Check 7-day memory      (drop anything already sent)
        |
        v
   Select top stories
        |
        v
   Fetch article text      (only for stories that made the cut)
        |
        v
   Write up and format
        |
        v
   Send email
        |
        v
   Save memory             (only after the email goes out)
```

Two things about the ordering are deliberate. The memory check happens after scoring
rather than before, so a suppressed story is replaced by the next best one rather than
leaving a gap. And article text is fetched only for the twenty odd stories that will
actually appear, which is a few dozen requests instead of one per article collected.

## The four sections

**🤖 AI Developments.** New models, research, company announcements, regulation,
acquisitions, and the chip and data centre stories underneath all of it.

**🌍 Global Politics.** Elections, conflicts, diplomacy, sanctions, trade disputes,
changes of government. Weighted towards events with international consequences.

**💻 World Technology.** Everything technical that is not already covered as AI:
semiconductors, cybersecurity, space, robotics, big tech regulation, major launches.

**🚀 Startup Funding Radar.** Recently announced rounds, with the details extracted where
the source states them, UK and Europe first.

A story appears in one section only, which is enforced rather than hoped for.

---

## Design decisions

### Anchor sources and discovery sources

**Problem.** A fixed list of publishers only ever tells me what those publishers covered.
Searching broadly instead returns a lot of noise.

**Decision.** Use both, and treat them differently. 45 hand picked feeds are the anchors,
each with a trust weight. 20 Google News RSS searches provide discovery. Anchors are
preferred when choosing which version of a story to lead with, and discovery-only stories
score lower unless several outlets corroborate them.

**Trade-off.** More sources means more noise, so this needs filtering to work at all: 26
blocked publishers (mostly stock tipping sites that flood technology searches) and 75
headline patterns for listicles, SEO spam and press release filler. That list is
maintenance I have signed myself up for.

### Grouping duplicate coverage

**Problem.** Five articles about one event should be one item, and Google News redirect
links make URL matching useless.

**Decision.** Group on text similarity: rare word weighted headline and summary tokens,
compared by containment so a terse headline matches a wordy one, plus a second merge pass.

**Trade-off.** Two write ups of the same event with no shared vocabulary stay separate.
Lowering the threshold merges more but starts collapsing genuinely different stories.
0.30 is where it currently sits and it is a compromise, not a solved problem.

### Rules based ranking

**Problem.** Something has to decide which twenty four stories out of six hundred go in.

**Decision.** A transparent weighted score built from corroboration, source trust, section
relevance, recency and gossip penalties.

**Trade-off.** It is a proxy, not a judgement. It rewards widely covered stories, which
under-serves anything important that has not been widely picked up yet. Every weight is
adjustable, and when the ordering looks wrong I can find out exactly why, which is not
true of a model. A model would rank better. This one I can debug.

### One story, one section

**Problem.** A funding round for an AI company is legitimately AI news and funding news.
Putting it in both wastes a slot and makes the brief feel repetitive.

**Decision.** Group first, then assign each group to exactly one section. Funding claims a
story first; everything else goes to the section with the strongest keyword evidence, and
a story with no real evidence for any section is dropped rather than filed by default.

**Trade-off.** Sometimes a story ends up somewhere I would not have put it. Making
sections mutually exclusive is what stops that being a wider problem.

### Seven day memory

**Problem.** Yesterday's big story scores higher today, so the brief repeated itself.

**Decision.** Record what was sent, compare headline word overlap against that record, drop
matches. Commit the record back to the repository so it survives GitHub wiping the machine.

**Trade-off.** Word overlap cannot distinguish a genuine development from a rehash. Some
real updates get suppressed and some rehashes get through. There is also a daily
housekeeping commit in the repository, which I decided I could live with.

### Failure handling

**Problem.** One dead feed should not cost me the whole briefing.

**Decision.** Every feed is fetched independently and a failure is logged and skipped.
Article fetches fail silently and fall back to whatever the feed gave. A corrupt memory
file starts a fresh one instead of stopping. Malformed entries are skipped without taking
the feed down with them. Quiet mornings, mostly weekends, widen the window to 48 hours
rather than sending an empty brief.

**Trade-off.** Degrading quietly means a feed can be broken for weeks without me noticing.
The run log says how many articles each source returned, which is the only real defence.

### Not inventing anything

**Problem.** The obvious way to make thin source material read well is to fill in the
gaps. In a news brief that is the one unacceptable failure.

**Decision.** Extractive summaries only, so the text is the publisher's. Glossary
definitions are hand written in advance, not generated per story. Funding fields the
source does not state are shown as "not stated in source". When there is genuinely nothing
but a headline, the brief says so and shows how other outlets worded it. Every story keeps
links to every source.

**Trade-off.** It reads less smoothly than generated prose and "simply explained" is
weaker than I want. I would rather have that than a brief I have to fact check.

---

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
  glossary.py             68 hand written plain English definitions
  formatter.py            HTML and plain text rendering
  email_sender.py         SMTP delivery
```

Each stage takes a list and returns a list, so any stage can be swapped or tested on its
own.

### Getting article text out of Google News

Worth documenting because the workaround is not obvious. Google News RSS gives you a
headline and a redirect link, and its summary field is a list of links to other outlets
rather than a summary. The redirect sits behind a consent wall that cannot be resolved
from a server, and I checked before giving up on it.

What Google News does give you is the publisher's domain. So when a story has no real
article URL, `article_fetcher.py` fetches that publisher's front page and looks for a link
whose text closely matches the headline. Correct matches score above 0.8 in testing and
wrong ones below 0.45, so the threshold sits at 0.62. Anything fetched is then checked
for the headline's distinctive words before it is used, which catches the case where the
link resolved to a section index and the "summary" would have been the publication's
own marketing copy.

On a typical run this gets real article text for around three quarters of the stories.
The rest fall back to showing how several outlets headlined the story.

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

Just the ranked headlines, useful when tuning the filters:

```bash
python main.py --dry-run
```

Check the email settings on their own:

```bash
python main.py --test-email
```

## Email configuration

Gmail needs an App Password, not your account password. Turn on 2-Step Verification, then
create one at https://myaccount.google.com/apppasswords and put it in `.env`:

```
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-character-app-password
EMAIL_TO=you@gmail.com
```

Then `python main.py`.

Two things that caught me out and are now handled in the code. Python installed from
python.org ships with no certificate store, so TLS to Gmail fails with
`CERTIFICATE_VERIFY_FAILED`; the code uses certifi's bundle rather than relying on the
system store. And values pasted into a `.env` file or a GitHub secret often carry a
trailing newline, which turns a hostname into something DNS cannot resolve, so every
setting is trimmed when it is read.

## Running it automatically

1. Push the repository to GitHub.
2. Settings, then Secrets and variables, then Actions. Add `SMTP_HOST`, `SMTP_PORT`,
   `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`.
3. Actions tab, Morning Brief, Run workflow, to test it straight away.

The schedule is in `.github/workflows/morning-brief.yml`:

```yaml
- cron: "30 6 * * *"   # 06:30 UTC daily
```

GitHub cron is always UTC and does not follow British Summer Time, so 06:30 UTC is 07:30
in London in summer and 06:30 in winter. The job needs `contents: write` permission
because it commits the memory file back after a successful run.

Two things worth knowing. Scheduled runs can be delayed by several minutes when GitHub is
busy. And GitHub disables scheduled workflows in repositories with no activity for 60
days, so if the brief stops arriving for no obvious reason, push any commit to re-enable
it.

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
publishers, `DISCOVERY_QUERIES` for the searches, `SECTION_KEYWORDS` for what belongs
where, `NOISE_PATTERNS` and `BLOCKED_SOURCES` for what to throw away. Add your own jargon
to `GLOSSARY` in `glossary.py` and it appears in "simply explained" whenever it comes up.

## Optional: adding an LLM summariser

`summariser.py` defines a `Summariser` interface with two implementations. Switching:

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

One request per story carrying the headline, the outlets covering it, and the fetched
article text. Structured outputs guarantee valid JSON back, which removes the "model
replied with prose instead" failure mode. Effort is set low because summarising is
faithful compression rather than hard reasoning. Refusal fallback is enabled, since a
brief covering wars and cyberattacks will occasionally trip a safety classifier.

Every story falls back to its extractive version if the call fails, so a model outage
degrades the brief rather than breaking it.

Measured on a real run of 24 stories: about 13,400 input tokens and 5,500 output tokens
a day.

| Model | Per day | Per month |
|---|---|---|
| Claude Opus 5 | ~$0.21 | ~$6 |
| Claude Sonnet 5 | ~$0.08 | ~$2.50 |
| Claude Haiku 4.5 | ~$0.04 | ~$1.25 |

Thinking tokens are billed as output, so budget roughly double. `LLM_MAX_STORIES` is a
hard ceiling on calls per run and is the real protection against a runaway bill.

Genuinely free options exist with caveats. A local Ollama is free and private but needs
your own machine awake at 7am, and is not practical on GitHub Actions where every run
would download the model weights again. Free API tiers cost nothing but are rate limited,
can change, and usually train on your inputs. Both work through
`LLM_PROVIDER=openai_compatible` with `LLM_BASE_URL` pointed at them.

## Known limitations

**Ranking is a proxy.** Corroboration is the best free signal for importance and it is
still only a signal. Genuinely important stories that nobody has picked up yet get
underrated by design.

**"Simply explained" is the weakest section.** Without a model it is a glossary lookup and
a category label, not a real explanation.

**Deduplication misses some pairs.** Two outlets can describe one event with no shared
vocabulary.

**The memory cannot tell development from repetition.** It compares headline words.

**Funding coverage has real gaps.** No paid database means it only sees announcements that
reached the feeds being read.

**Some major publications have no usable free feed,** so the source mix is skewed towards
those that do.

**"Last 24 hours" is approximate.** Feeds report times inconsistently and Google News
`when:1d` is its own approximation. The window is 26 hours by default and widens to 48
on quiet mornings.

**Google News RSS is undocumented.** Free and stable in practice, but not a supported API,
and it could change without notice.

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
