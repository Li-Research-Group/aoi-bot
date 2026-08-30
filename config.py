"""
Central configuration for the group articles-of-interest (AOI) feed pipeline.

Fill in the RSS feed URLs below (see README.md for how to find each
publisher's feed). Everything else can be edited freely as your group's
topics or journal list change over time -- this file is the only thing
you should need to touch for routine adjustments.
"""

# --- Slack -------------------------------------------------------------

# The channel the weekly digest posts to. Use the channel ID (starts with
# "C..."), not the #name -- right-click the channel in Slack > "View
# channel details" > scroll down to find the ID.
SLACK_CHANNEL_ID = "C0BTP4UT4F3"

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

    # Elsevier / ScienceDirect -- RSS link in the journal page sidebar
    "Algal Research": "https://rss.sciencedirect.com/publication/science/22119264",
    "Bioresource Technology": "https://rss.sciencedirect.com/publication/science/09608524",
    "Computers & Chemical Engineering": "https://rss.sciencedirect.com/publication/science/00981354",
    "Construction and Building Materials": "https://rss.sciencedirect.com/publication/science/09500618",
    "Journal of Cleaner Production": "https://rss.sciencedirect.com/publication/science/09596526",
    "Resources, Conservation and Recycling": "https://rss.sciencedirect.com/publication/science/09213449",
    "Resources, Conservation and Recycling Advances": "https://rss.sciencedirect.com/publication/science/26673789",
    "Waste Management": "https://rss.sciencedirect.com/publication/science/0956053X",
    "Waste Management Bulletin": "https://rss.sciencedirect.com/publication/science/29497507",
    "Water Research": "https://rss.sciencedirect.com/publication/science/00431354",
    "Water Research X": "https://rss.sciencedirect.com/publication/science/25899147",

    # Springer Nature (nature.com) -- https://www.nature.com/<journal-code>/rss
    "Nature Chemical Engineering": "https://www.nature.com/natchemeng/rss",
    "Nature Communications": "https://www.nature.com/ncomms/rss",
    "Nature Energy": "https://www.nature.com/nenergy/rss",
    "Nature Sustainability": "https://www.nature.com/natsustain/rss",
    "Nature Water": "https://www.nature.com/natwater/rss",

    # Springer Nature (SpringerLink) -- link.springer.com/search.rss?facet-journal-id=<id>
    # (JIE moved from Wiley to Springer Nature for 2026-2030; journal id 44498)
    "Journal of Industrial Ecology": "https://link.springer.com/search.rss?facet-content-type=Article&facet-journal-id=44498&channel-name=Journal+of+Industrial+Ecology",
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

# --- Broader-reading feed (separate category, not a research-topic match) --
# News/Career/Comment feeds -- NOT the research-article feeds for these
# journals. Kept structurally separate so cadence/scope can be tuned later
# without touching the topic pipeline above.
BROADER_READING_FEEDS = {
    "Nature Careers": "https://www.nature.com/subjects/careers.rss",
    "Science Careers": "https://www.science.org/digital-feed/careers-articles",
}

# --- Pipeline knobs --------------------------------------------------------

LOOKBACK_DAYS = 8          # how far back to check for "new" papers each run
MAX_PAPERS_PER_TOPIC = 4   # cap per topic per week, to keep the digest short
STATE_FILE = "state/paper_log.json"
