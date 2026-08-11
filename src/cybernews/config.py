import os
import json
from pathlib import Path

# Base directory of the project (cybernews/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Default database/storage path
DEFAULT_DB_PATH = BASE_DIR / "data" / "news.jsonl"
DB_PATH = Path(os.getenv("CYBERNEWS_DB_PATH", str(DEFAULT_DB_PATH)))

# Feeds JSON storage path
FEEDS_JSON_PATH = DB_PATH.parent / "feeds.json"

# Cache duration in seconds (default 5 minutes)
CACHE_DURATION_SECS = int(os.getenv("CYBERNEWS_CACHE_DURATION", "300"))

# Default limit of articles to display in the CLI
DEFAULT_LIMIT = int(os.getenv("CYBERNEWS_DEFAULT_LIMIT", "20"))

# Default configuration of reputable RSS feeds
DEFAULT_RSS_FEEDS = {
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
    "Dark Reading": "https://www.darkreading.com/rss.xml",
    "SecurityWeek": "https://www.securityweek.com/feed/",
}

def load_configured_feeds() -> dict[str, str]:
    """Loads configured RSS feeds from feeds.json, or initializes with defaults."""
    if FEEDS_JSON_PATH.exists():
        try:
            with open(FEEDS_JSON_PATH, "r", encoding="utf-8") as f:
                feeds = json.load(f)
                if isinstance(feeds, dict):
                    return feeds
        except Exception:
            pass
    # If file doesn't exist or is malformed, write and return defaults
    save_configured_feeds(DEFAULT_RSS_FEEDS)
    return DEFAULT_RSS_FEEDS

def save_configured_feeds(feeds: dict[str, str]) -> None:
    """Saves configured RSS feeds to feeds.json."""
    try:
        FEEDS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FEEDS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(feeds, f, indent=4)
    except Exception:
        pass
