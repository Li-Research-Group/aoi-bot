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
# name -> RSS/Atom feed URL for that journal's latest articles.
# See README.md "Finding RSS feeds" for how to get each of these.
JOURNALS = {
    "Energy & Environmental Science": "FILL_IN_RSS_URL",
    "Bioresource Technology": "FILL_IN_RSS_URL",
    "ACS Sustainable Chemistry & Engineering": "FILL_IN_RSS_URL",
    "ACS ES&T Engineering": "FILL_IN_RSS_URL",
    "ACS ES&T Water": "FILL_IN_RSS_URL",
    "Environmental Science & Technology": "FILL_IN_RSS_URL",
    "Environmental Science & Technology Letters": "FILL_IN_RSS_URL",
    "Journal of Cleaner Production": "FILL_IN_RSS_URL",
    "Green Chemistry": "FILL_IN_RSS_URL",
    "Algal Research": "FILL_IN_RSS_URL",
    "Water Research": "FILL_IN_RSS_URL",
    "Water Research X": "FILL_IN_RSS_URL",
    "Computers & Chemical Engineering": "FILL_IN_RSS_URL",
    "Journal of Industrial Ecology": "FILL_IN_RSS_URL",
    "Resources, Conservation and Recycling": "FILL_IN_RSS_URL",
    "Waste Management": "FILL_IN_RSS_URL",
    "Nature Water": "FILL_IN_RSS_URL",
    "Nature Sustainability": "FILL_IN_RSS_URL",
    "Nature Energy": "FILL_IN_RSS_URL",
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
    "Nature News & Comment": "FILL_IN_RSS_URL",
    "Science Careers": "FILL_IN_RSS_URL",
}

# --- Pipeline knobs --------------------------------------------------------

LOOKBACK_DAYS = 8          # how far back to check for "new" papers each run
MAX_PAPERS_PER_TOPIC = 4   # cap per topic per week, to keep the digest short
STATE_FILE = "state/paper_log.json"
