# Group Paper Feed

Automated weekly literature digest for the group's Slack. Pulls candidate
papers from journal RSS feeds (fast, guaranteed same-day coverage for
known journals) and OpenAlex topic search (broader net for anything
outside the tracked journal list), filters them for relevance with the
Claude API, and posts a tagged digest to Slack as a header message with
each paper as a threaded reply -- so people can react 👍/👎 on individual
papers. A monthly job reads those reactions back and posts a leaderboard
of which journals/topics are actually earning their keep, so you can
adjust the config over time based on real signal instead of a guess.

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

### 4. Fill in the RSS feed URLs in `config.py`

Every entry currently says `"FILL_IN_RSS_URL"`. Here's where to find each
publisher's feed:

- **ACS journals** (Sustainable Chem & Eng, ES&T, ES&T Water, ES&T
  Engineering, ES&T Letters): go to the journal's homepage on
  pubs.acs.org, look for the RSS icon (usually near "Current Issue" or
  in the page footer) -- ACS publishes an "ASAP" feed that fires the
  moment an article goes live, which is the one you want, not the
  issue-based feed.
- **Elsevier / ScienceDirect journals** (Bioresource Technology, Journal
  of Cleaner Production, Algal Research, Water Research, Water Research
  X, Computers & Chemical Engineering, Resources Conservation and
  Recycling, Waste Management): on the journal's ScienceDirect page,
  there's an RSS link in the right-hand sidebar or under "Guide for
  Authors" navigation.
- **RSC journals** (Green Chemistry, Energy & Environmental Science):
  pubs.rsc.org journal homepages have an RSS link near the top of the
  page, usually labeled "RSS Feed" or via the "Latest articles" tab.
- **Wiley** (Journal of Industrial Ecology): the journal's Wiley Online
  Library homepage has an RSS link under "Get New Content Alerts" or in
  the page footer.
- **Nature journals** (Nature Water, Nature Sustainability, Nature
  Energy): `https://www.nature.com/<journal-code>.rss` -- e.g.
  `https://www.nature.com/nwater.rss`. Check the journal's homepage
  footer to confirm the exact code.

If a publisher makes this hard to find, search "`<journal name> RSS
feed`" -- nearly all of them have one, it's just not always prominently
linked.

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
| `sources.py` | RSS + OpenAlex fetching, dedupe |
| `relevance.py` | Claude API relevance scoring |
| `slack_post.py` | Formats and posts the Slack digest |
| `state.py` | Reads/writes `state/paper_log.json` |
| `run_weekly.py` | Weekly entry point (wires the above together) |
| `track_reactions.py` | Monthly entry point -- reaction leaderboard |
| `.github/workflows/weekly.yml` | Cron for the weekly digest |
| `.github/workflows/monthly.yml` | Cron for the monthly report |
