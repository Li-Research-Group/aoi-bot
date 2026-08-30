# Group Paper Feed

Automated weekly literature digest for the group's Slack. Pulls candidate
papers from four lanes -- journal RSS feeds (fast, same-day coverage for
journals with a usable feed), an OpenAlex query per tracked journal by
ISSN (backstop for journals with no feed / a stale feed / a short rolling
feed), OpenAlex keyword search per topic (broader net for anything
outside the tracked journal list), and an OpenAlex query per **followed
author** (every recent paper by people the group tracks, regardless of
topic) -- filters the first three for relevance with the Claude API
(the followed-author lane bypasses that and gets its own digest section),
and posts a tagged digest to Slack -- a header message, then one message
per paper -- so people can react 👍/👎 on individual papers. A monthly job reads those reactions back and posts a report --
the pipeline funnel (collected → scored → relevant → posted, per lane),
Claude cost per run, dead-feed alerts, engagement rate, the title-only
vs. abstract cohort split, staleness, and per-journal / per-topic 👍
rates -- so you can adjust the config over time based on real signal
instead of a guess.

Coverage note: OpenAlex carries abstracts for ACS, Springer Nature and
Wiley but not Elsevier, and Elsevier RSS feeds carry no abstract either --
so Elsevier papers (Bioresource Technology, Water Research, Journal of
Cleaner Production, ...) reach the pipeline with title + DOI + date only.
`relevance.py` scores those on the title alone (tracked journals only) and
the digest flags them "matched on title only". RSC is thin for a different
reason: OpenAlex lags RSC badly and `feeds.rsc.org` is a stale mirror.

## One-time setup

### 1. Create the Slack app

1. Go to https://api.slack.com/apps -> "Create New App" -> "From scratch".
2. Under **OAuth & Permissions**, add these Bot Token Scopes:
   - `chat:write` (post messages)
   - `reactions:read` (read reaction counts)
   - `channels:history` (or `groups:history` if the channel is private)
   - `users:read` (resolve reactor IDs to initials for the monthly
     report's participation line -- names are reduced to initials, never
     shown in full)
3. Install the app to your workspace, then copy the **Bot User OAuth
   Token** (starts with `xoxb-`).
4. Invite the bot to your group's channel: `/invite @your-bot-name` in
   that channel.
5. Get the channel ID: right-click the channel name in Slack -> "View
   channel details" -> ID is at the bottom. Paste it into
   `config.py` as `SLACK_CHANNEL_ID`.

### 2. Get an Anthropic API key

From https://console.anthropic.com -- this is what scores each abstract
for relevance. Costs are small: a few hundred abstracts a week at a few
hundred tokens each is a fraction of a cent per paper.

### 3. Push this repo to GitHub and add secrets

In the repo's **Settings > Secrets and variables > Actions**, add:
- `SLACK_BOT_TOKEN` -- the `xoxb-...` token from step 1
- `ANTHROPIC_API_KEY` -- from step 2

That's it for infrastructure -- GitHub Actions runs the two workflows on
their own schedule from here, no server needed.

### 4. Journals in `config.py`

Two maps drive journal coverage:

- **`JOURNALS`** -- name -> RSS feed URL, for journals with a usable feed.
  Feed URL patterns per publisher:
  - **ACS**: `https://pubs.acs.org/rss/<code>/asap.xml` -- the "ASAP" feed
    (fires on publication), not the issue feed.
  - **RSC**: `http://feeds.rsc.org/rss/<code>`. Note this mirror lags; the
    live `pubs.rsc.org` feed is Cloudflare-blocked to scripts.
  - **Nature (nature.com)**: `https://www.nature.com/<code>/rss` -- these
    are RSS 1.0 / RDF and carry the abstract in `<content:encoded>`.
  - **SpringerLink** (e.g. Journal of Industrial Ecology, journal id
    44498): `https://link.springer.com/search.rss?facet-content-type=Article&facet-journal-id=<id>&channel-name=<name>`
  - **Elsevier / ScienceDirect**: intentionally omitted -- their feeds
    carry no abstract, date, or DOI. Covered by `JOURNAL_ISSNS` instead
    (title-only; see the coverage note above).
  - **Nature Communications**: intentionally omitted from both maps -- too
    broad, almost everything is off-topic.

- **`JOURNAL_ISSNS`** -- name -> ISSN-L for *every* tracked journal.
  Queried directly from OpenAlex by ISSN each run, as a backstop to the
  RSS lane. Find an ISSN-L with
  `https://api.openalex.org/sources?search=<journal name>` (the `issn_l`
  field of the first result). Keep the keys in sync with `JOURNALS` where
  a journal is in both.

### 4b. Followed authors (`FOLLOWED_AUTHORS` in `config.py`)

Optional. `name -> OpenAlex author ID or ORCID` for people whose every
recent paper you want to see, on-topic or not. Either works: an OpenAlex
ID from `https://api.openalex.org/authors?search=<name>` (the tail of the
`id` field, `A5023888391`), or a bare ORCID (`0000-0003-2078-1126`) --
the ORCID is easier to verify. These papers get their
own **Followed authors** section in the digest, capped at
`MAX_PAPERS_PER_AUTHOR` per run, and skip the relevance filter (so a
prolific author is capped, not scored away). A followed author's paper is
pulled out of the topic pipeline before scoring -- it shows once, in the
authors section. Leave the map empty to disable the lane.

For the **Broader Reading** feeds (`BROADER_READING_FEEDS` in
`config.py`), use the *News & Comment* or *Careers* section feeds for
Nature/Science, not their research-article feeds:
- Nature News: `https://www.nature.com/subjects/careers.rss` (check
  nature.com for the current News/Comment feed URL, this moves
  occasionally)
- Science Careers: look for the RSS link on
  https://www.science.org/careers

### 5. Test it manually before trusting the schedule

From the repo's **Actions** tab, run the "Weekly paper digest" workflow
manually (`workflow_dispatch`) once you've filled in at least a few RSS
URLs, and check that the digest lands in Slack looking right before
relying on the Monday cron.

### 6. (Optional) Set up the dry-run channel

The **"Dry run (test channel, no Claude)"** workflow runs the real
pipeline against a separate private Slack channel, with the Claude
relevance call swapped for a keyword heuristic -- so it costs **zero
Claude tokens** and never touches the live channel or
`state/paper_log.json`. To enable it:

1. Create a private channel (e.g. `aoi-test`) and `/invite` the bot into it.
2. Add a repository **variable** (not secret) `AOI_TEST_CHANNEL_ID` =
   that channel's ID, under *Settings > Secrets and variables > Actions
   > Variables*.

Then trigger it from the Actions tab (`workflow_dispatch`), choosing
`weekly` or `monthly`. Dry-run posts go to `aoi-test`, the rendered
output is also written to the run's summary page, and dry-run state
lives in `state/paper_log.dryrun.json` (committed back so a `monthly`
dry-run can read reactions left on a prior `weekly` dry-run). It is
driven by three env vars the workflow sets -- `DRY_RUN=1`,
`SLACK_CHANNEL_ID`, `STATE_FILE` -- which all default to the production
values when unset.

Tests run on every push and PR via the **CI** workflow (`pytest`, no
network, no secrets). Run them locally with
`pip install -r requirements-dev.txt && python -m pytest`.

## How the feedback loop works

- React 👍 or 👎 directly on any paper's message in Slack.
- On the 1st of each month, the "Monthly feedback report" workflow posts:
  - **Pipeline** -- across the month's runs: the collected → scored →
    relevant → posted funnel with yield %, papers posted by lane,
    cross-lane duplicates removed, average Claude cost per run, and a
    ⚠️ alert for any feed that returned nothing on *every* run (likely
    breakage). Sourced from `state["runs"]`, written each weekly run.
  - **Posted papers** -- count, engagement rate (% of papers that got
    any reaction), median publish→post lag, the abstract-scored vs.
    title-only (Elsevier) cohort 👍 rates, per-tag volume, and the
    most-upvoted / net-downvoted papers.
  - **By journal / by topic** -- papers posted and 👍 rate.
  - **Followed authors** -- papers posted and 👍 rate per followed
    author, so you can see which follows are paying off.
  - **Participation** -- reactions given per person, by initials only (a
    participation view, deliberately not a per-person 👍-vs-👎 scoreboard).
- This is a report for a human to act on, not an auto-pilot: if a
  journal is consistently near 0% upvoted after a couple months, that's
  a signal to drop it from `config.py` (or narrow its topic's keywords).
  If a specific author keeps showing up with upvotes -- in the digest or
  the by-journal breakdown -- add them to `FOLLOWED_AUTHORS`.
- Adjusting the pipeline going forward is just editing `config.py` --
  add/remove journals under `JOURNALS`, tweak keyword lists or add new
  topics under `TOPICS`, add people to `FOLLOWED_AUTHORS`. No other file
  should need to change for routine tuning.

## Tuning knobs (in `config.py`)

- `LOOKBACK_DAYS` -- how far back each run looks for "new" papers
  (default 8, to comfortably cover a 7-day gap between runs).
- `MAX_PAPERS_PER_TOPIC` -- caps the weekly digest length per topic
  (default 4).
- `MAX_PAPERS_PER_AUTHOR` -- caps the followed-author section per author
  per run (default 3).

Environment overrides (set only by the dry-run workflow; production
leaves them unset): `SLACK_CHANNEL_ID`, `STATE_FILE`, and `DRY_RUN`
(when truthy, `run_weekly.py` uses the keyword heuristic instead of
Claude and labels the digest `[DRY RUN]`).

## File overview

| File | Purpose |
|---|---|
| `config.py` | Journals, topics, feeds, Slack channel -- the only file you should need to edit routinely |
| `sources.py` | RSS + OpenAlex (journal / keyword / followed-author) fetching, feed parsing, dedupe |
| `relevance.py` | Claude relevance scoring + `heuristic_filter` (the offline keyword stand-in for `DRY_RUN`) |
| `stats.py` | Pure aggregation: per-run stats record + monthly-report roll-ups (fully unit-tested) |
| `slack_post.py` | Formats and posts the Slack digest |
| `state.py` | Reads/writes the state file (`posted` + `runs`) |
| `run_weekly.py` | Weekly entry point (wires the above together, writes a run stats record) |
| `track_reactions.py` | Monthly entry point -- the feedback report |
| `tests/` | `pytest` unit + integration tests (no network); `pip install -r requirements-dev.txt` |
| `.github/workflows/weekly.yml` | Cron for the weekly digest |
| `.github/workflows/monthly.yml` | Cron for the monthly report |
| `.github/workflows/ci.yml` | Runs `pytest` on every push and PR |
| `.github/workflows/dry-run.yml` | Manual: real pipeline → `aoi-test`, keyword heuristic instead of Claude |
