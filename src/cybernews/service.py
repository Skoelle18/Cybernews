import logging
from typing import Any, Dict, List

from cybernews.config import load_configured_feeds
from cybernews.models import Article, SourceStatus
from cybernews.collectors.rss import fetch_feed
from cybernews.processing.normalize import normalize_articles
from cybernews.processing.deduplicate import deduplicate_articles
from cybernews.processing.categorize import categorize_articles
from cybernews.state import StateManager

logger = logging.getLogger("cybernews.service")

def get_latest_news(
    state_manager: StateManager,
    feeds: Dict[str, str] = None,
    force_refresh: bool = False
) -> List[Article]:
    """Coordinates RSS collection, normalization, deduplication, and categorization.

    Retrieves from the in-memory cache if the cache is valid, unless force_refresh is True.
    """
    if feeds is None:
        feeds = load_configured_feeds()

    if not force_refresh and not state_manager.is_cache_expired():
        logger.info("Returning cached articles from StateManager.")
        return state_manager.current_articles

    logger.info("StateManager cache is expired or force refresh requested. Fetching live RSS feeds.")

    raw_feed_data = []
    source_statuses = {}

    for name, url in feeds.items():
        try:
            entries, status = fetch_feed(name, url)
            source_statuses[name] = status
            if status.success:
                raw_feed_data.append((entries, name))
        except Exception as e:
            # Backup safety catcher: ensuring a crash in one source doesn't block the rest
            logger.error("Failsafe caught exception for feed '%s': %s", name, str(e))
            source_statuses[name] = SourceStatus(
                name=name,
                url=url,
                success=False,
                articles_count=0,
                error_message=str(e)
            )

    # Convert all raw entries to Article objects
    all_articles = []
    for entries, source_name in raw_feed_data:
        normalized = normalize_articles(entries, source_name)
        all_articles.extend(normalized)

    # Process: Deduplicate -> Categorize -> Sort
    deduped = deduplicate_articles(all_articles)
    categorized = categorize_articles(deduped)
    
    # Sort descending by published date (newest first)
    sorted_articles = sorted(categorized, key=lambda x: x.published_at, reverse=True)

    # Update in-memory state manager
    state_manager.update(sorted_articles, source_statuses)

    return state_manager.current_articles

def get_in_memory_stats(state_manager: StateManager) -> Dict[str, Any]:
    """Compiles statistics for in-memory articles and sources."""
    articles = state_manager.current_articles
    total = len(articles)

    success_sources = sum(1 for s in state_manager.source_statuses.values() if s.success)
    failed_sources = sum(1 for s in state_manager.source_statuses.values() if not s.success)

    if total == 0:
        return {
            "total": 0,
            "categories": {},
            "sources": {},
            "oldest_pub": None,
            "latest_pub": None,
            "last_fetch_time": state_manager.last_fetch_time,
            "success_sources": success_sources,
            "failed_sources": failed_sources,
        }

    categories = {}
    sources = {}
    oldest_pub = None
    latest_pub = None

    for art in articles:
        categories[art.category] = categories.get(art.category, 0) + 1
        sources[art.source] = sources.get(art.source, 0) + 1

        pub = art.published_at
        if oldest_pub is None or pub < oldest_pub:
            oldest_pub = pub
        if latest_pub is None or pub > latest_pub:
            latest_pub = pub

    return {
        "total": total,
        "categories": categories,
        "sources": sources,
        "oldest_pub": oldest_pub,
        "latest_pub": latest_pub,
        "last_fetch_time": state_manager.last_fetch_time,
        "success_sources": success_sources,
        "failed_sources": failed_sources,
    }
