# Group Paper Feed

Automated weekly literature digest for the group's Slack. Pulls candidate
papers from three lanes -- journal RSS feeds (fast, same-day coverage for
journals with a usable feed), an OpenAlex query per tracked journal by
ISSN (backstop for journals with no feed / a stale feed / a short rolling
feed), and OpenAlex keyword search per topic (broader net for anything
outside the tracked journal list) -- filters them for relevance with the
Claude API, and posts a tagged digest to Slack as a header message with
each paper as a threaded reply -- so people can react 👍/👎 on individual
papers. A monthly job reads those reactions back and posts a leaderboard
of which journals/topics are actually earning their keep, so you can
adjust the config over time based on real signal instead of a guess.

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

## How the feedback loop works

- React 👍 or 👎 directly on any paper's message in Slack.
- On the 1st of each month, the "Monthly feedback report" workflow posts
  a breakdown by journal and by topic: how many papers each contributed
  this month, and what fraction were upvoted.
- This is a report for a human to act on, not an auto-pilot: if a
  journal is consistently near 0% upvoted after a couple months, that's
  a signal to drop it from `config.py` (or narrow its topic's keywords).
  If a specific author keeps showing up with upvotes, that's a signal to
  add an author-specific OpenAlex query for them.
- Adjusting the pipeline going forward is just editing `config.py` --
  add/remove journals under `JOURNALS`, tweak keyword lists or add new
  topics under `TOPICS`. No other file should need to change for routine
  tuning.

## Tuning knobs (in `config.py`)

- `LOOKBACK_DAYS` -- how far back each run looks for "new" papers
  (default 8, to comfortably cover a 7-day gap between runs).
- `MAX_PAPERS_PER_TOPIC` -- caps the weekly digest length per topic
  (default 4).

## File overview

| File | Purpose |
|---|---|
| `config.py` | Journals, topics, feeds, Slack channel -- the only file you should need to edit routinely |
| `sources.py` | RSS + OpenAlex (journal + keyword) fetching, feed parsing, dedupe |
| `relevance.py` | Claude API relevance scoring |
| `slack_post.py` | Formats and posts the Slack digest |
| `state.py` | Reads/writes `state/paper_log.json` |
| `run_weekly.py` | Weekly entry point (wires the above together) |
| `track_reactions.py` | Monthly entry point -- reaction leaderboard |
| `.github/workflows/weekly.yml` | Cron for the weekly digest |
| `.github/workflows/monthly.yml` | Cron for the monthly report |
