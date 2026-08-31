"""
Central configuration for the group articles-of-interest (AOI) feed pipeline.

Fill in the RSS feed URLs below (see README.md for how to find each
publisher's feed). Everything else can be edited freely as your group's
topics or journal list change over time -- this file is the only thing
you should need to touch for routine adjustments.
"""

import os

# --- Slack -------------------------------------------------------------

# The channel the weekly digest posts to. Use the channel ID (starts with
# "C..."), not the #name -- right-click the channel in Slack > "View
# channel details" > scroll down to find the ID.
# Overridable via the SLACK_CHANNEL_ID env var so the dry-run workflow can
# point at a test channel without touching this file.
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID") or "C05M84JAZUZ" # aoi: C05M84JAZUZ; aoi-test: C0BTP4UT4F3

# --- Journals ------------------------------------------------------------
# name -> RSS/Atom feed URL for that journal's latest articles. Grouped by
# publisher because the feed URL follows a per-publisher pattern -- see
# README.md "Finding RSS feeds" for where each publisher exposes theirs.
# The grouping is cosmetic; downstream code iterates the dict, not order.
JOURNALS = {
    # RSC -- feeds.rsc.org/rss/<code>, or the "RSS Feed" link on the
    # journal homepage at pubs.rsc.org
    "Energy & Environmental Science": "http://feeds.rsc.org/rss/ee",
    "Green Chemistry": "http://feeds.rsc.org/rss/gc",

    # ACS -- pubs.acs.org, use the "ASAP" feed (fires on publication),
    # not the issue-based feed
    "ACS Engineering Au": "https://pubs.acs.org/rss/aeacb3/asap.xml",
    "ACS Environmental Au": "https://pubs.acs.org/rss/aeacc4/asap.xml",
    "ACS ES&T Engineering": "https://pubs.acs.org/rss/aeecco/asap.xml",
    "ACS ES&T Water": "https://pubs.acs.org/rss/aewcaa/asap.xml",
    "ACS Sustainable Chemistry & Engineering": "https://pubs.acs.org/rss/ascecg/asap.xml",
    "ACS Sustainable Resource Management": "https://pubs.acs.org/rss/asrmcd/asap.xml",
    "Environmental Science & Technology": "https://pubs.acs.org/rss/esthag/asap.xml",
    "Environmental Science & Technology Letters": "https://pubs.acs.org/rss/estlcu/asap.xml",

    # Elsevier / ScienceDirect journals are covered by the OpenAlex journal
    # lane (JOURNAL_ISSNS) instead of RSS: their feeds carry no abstract,
    # no date and no DOI, so an RSS entry can't be filtered or scored.

    # Springer Nature (nature.com) -- https://www.nature.com/<journal-code>/rss
    # (Nature Communications deliberately omitted -- too broad, ~all off-topic)
    "Nature Chemical Engineering": "https://www.nature.com/natchemeng/rss",
    "Nature Energy": "https://www.nature.com/nenergy/rss",
    "Nature Sustainability": "https://www.nature.com/natsustain/rss",
    "Nature Water": "https://www.nature.com/natwater/rss",

    # Springer Nature (SpringerLink) -- link.springer.com/search.rss?facet-journal-id=<id>
    # (JIE moved from Wiley to Springer Nature for 2026-2030; journal id 44498)
    "Journal of Industrial Ecology": "https://link.springer.com/search.rss?facet-content-type=Article&facet-journal-id=44498&channel-name=Journal+of+Industrial+Ecology",
}

# --- Journal ISSNs (OpenAlex journal lane) -----------------------------
# name -> ISSN-L. Every tracked journal, queried directly from OpenAlex by
# ISSN each run. This backstops the RSS lane: it covers journals with no
# usable feed (all the Elsevier titles), a stale feed (RSC's feeds.rsc.org
# mirror), or a rolling feed that only shows the last ~10 articles (ACS),
# and it gives every paper a canonical DOI so the lanes dedupe cleanly.
# OpenAlex has abstracts for ACS / Springer Nature / Wiley but NOT Elsevier
# -- Elsevier papers arrive with title + DOI + date only, and relevance.py
# scores those on the title alone (only tracked journals get that fallback).
# Keep the keys in sync with JOURNALS where a journal appears in both.
JOURNAL_ISSNS = {
    # RSC
    "Energy & Environmental Science": "1754-5692",
    "Green Chemistry": "1463-9262",
    # ACS
    "ACS Engineering Au": "2694-2488",
    "ACS Environmental Au": "2694-2518",
    "ACS ES&T Engineering": "2690-0645",
    "ACS ES&T Water": "2690-0637",
    "ACS Sustainable Chemistry & Engineering": "2168-0485",
    "ACS Sustainable Resource Management": "2837-1445",
    "Environmental Science & Technology": "0013-936X",
    "Environmental Science & Technology Letters": "2328-8930",
    # Elsevier / ScienceDirect (OpenAlex-only; no abstracts available)
    "Algal Research": "2211-9264",
    "Bioresource Technology": "0960-8524",
    "Computers & Chemical Engineering": "0098-1354",
    "Construction and Building Materials": "0950-0618",
    "Journal of Cleaner Production": "0959-6526",
    "Resources, Conservation and Recycling": "0921-3449",
    "Resources, Conservation and Recycling Advances": "2667-3789",
    "Waste Management": "0956-053X",
    "Waste Management Bulletin": "2949-7507",
    "Water Research": "0043-1354",
    "Water Research X": "2589-9147",
    # Springer Nature
    "Journal of Industrial Ecology": "1088-1980",
    "Nature Chemical Engineering": "2948-1198",
    "Nature Energy": "2058-7546",
    "Nature Sustainability": "2398-9629",
    "Nature Water": "2731-6084",
}

# --- Topics --------------------------------------------------------------
# Each topic has:
#   keywords   -- short phrases used both for the OpenAlex broad search and
#                 as hints in the relevance-check prompt
#   journals   -- which JOURNALS entries are the primary home for this
#                 topic (used for the RSS half of the pipeline; not
#                 exclusive -- OpenAlex can surface hits from elsewhere too)
TOPICS = {
    "Sargassum/Seaweed (HTL, AD, arrested AD)": {
        "keywords": [
            "Sargassum", "brown seaweed", "macroalgae hydrothermal liquefaction",
            "seaweed anaerobic digestion", "arrested anaerobic digestion",
        ],
        "journals": ["Algal Research", "Bioresource Technology", "Energy & Environmental Science"],
    },
    "Biobinder (TEA/LCA/supply chain)": {
        "keywords": [
            "biobinder", "bio-based asphalt binder", "biocrude binder supply chain",
        ],
        "journals": ["Journal of Cleaner Production", "ACS Sustainable Chemistry & Engineering", "Green Chemistry"],
    },
    "Hydrothermal Microplastic Degradation": {
        "keywords": [
            "microplastic hydrothermal degradation", "microplastic thermal valorization",
        ],
        "journals": ["Environmental Science & Technology", "Environmental Science & Technology Letters", "Water Research"],
    },
    "Process Modeling Tools (BioSTEAM/QSDsan-like)": {
        "keywords": [
            "techno-economic analysis software", "process simulation open source",
            "BioSTEAM", "QSDsan",
        ],
        "journals": ["Computers & Chemical Engineering"],
    },
    "New TEA/LCA Methods": {
        "keywords": [
            "techno-economic analysis methodology", "life cycle assessment methodology",
            "uncertainty analysis TEA LCA",
        ],
        "journals": ["Journal of Industrial Ecology", "Journal of Cleaner Production", "ACS Sustainable Chemistry & Engineering"],
    },
    "Cell-Free Systems Market Analysis/TEA": {
        "keywords": [
            "cell-free protein synthesis techno-economic", "cell-free biomanufacturing market",
        ],
        "journals": [],  # no dedicated journal -- relies on the OpenAlex/author search half
    },
    "Cement/Concrete Recycling TEA/LCA": {
        "keywords": [
            "recycled concrete aggregate life cycle assessment", "construction demolition waste TEA",
            "cement recycling techno-economic",
        ],
        "journals": ["Resources, Conservation and Recycling", "Waste Management", "Journal of Cleaner Production"],
    },
    "Water/Wastewater Treatment (teaching)": {
        "keywords": [
            "novel wastewater treatment process", "emerging contaminant removal",
            "resource recovery wastewater",
        ],
        "journals": ["ACS ES&T Water", "ACS ES&T Engineering", "Water Research", "Water Research X"],
    },
    "Cross-Cutting / High-Impact": {
        "keywords": [
            "sustainability energy transition", "circular economy waste valorization",
        ],
        "journals": ["Energy & Environmental Science", "Nature Water", "Nature Sustainability", "Nature Energy"],
    },
}

# --- Followed authors -------------------------------------------------
# name -> OpenAlex author ID ("A5023888391") OR ORCID ("0000-0003-2078-1126").
# Every recent paper by these people is surfaced in its own digest section
# regardless of topic match -- a true "follow" -- capped at
# MAX_PAPERS_PER_AUTHOR per run. Find an OpenAlex ID at
# https://api.openalex.org/authors?search=<name> (the "id" field of the
# best match, tail after the last slash); an ORCID works just as well and
# is easier to verify. A followed author's paper is pulled out of the
# topic pipeline before relevance scoring, so it shows in the
# Followed-authors section only, never twice.
FOLLOWED_AUTHORS: dict[str, str] = {
    # Corinne Scown (LBNL / JBEI) -- TEA & LCA of biofuels and bioproducts.
    "Corinne Scown": "0000-0003-2078-1126",  # ORCID
}

# --- Broader-reading feed (separate category, not a research-topic match) --
# News/Career/Comment feeds -- NOT the research-article feeds for these
# journals. Kept structurally separate so cadence/scope can be tuned later
# without touching the topic pipeline above.
BROADER_READING_FEEDS = {
    "Nature Careers": "https://www.nature.com/subjects/careers.rss",
    "Science Careers": "https://www.science.org/digital-feed/careers-articles",
}

# --- Pipeline knobs --------------------------------------------------------

LOOKBACK_DAYS = 8           # how far back to check for "new" papers each run
MAX_PAPERS_PER_TOPIC = 4    # cap per topic per week, to keep the digest short
MAX_PAPERS_PER_AUTHOR = 3   # cap per followed author per run

# Overridable via the STATE_FILE env var -- the dry-run workflow points at
# a separate file so test posts never pollute the real dedupe log.
STATE_FILE = os.environ.get("STATE_FILE") or "state/paper_log.json"

# Set by the dry-run workflow. When true, run_weekly.py skips the Claude
# relevance call (keyword heuristic instead) and labels the digest.
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
