from datetime import datetime, timezone
from typing import Dict, List, Optional

from cybernews.config import CACHE_DURATION_SECS
from cybernews.models import Article, SourceStatus

class StateManager:
    """Manages temporary, in-memory application state and cache expiry."""

    def __init__(self, cache_duration_secs: int = CACHE_DURATION_SECS):
        self.current_articles: List[Article] = []
        self.last_fetch_time: Optional[datetime] = None
        self.source_statuses: Dict[str, SourceStatus] = {}
        self.cache_duration_secs: int = cache_duration_secs

    def is_cache_expired(self) -> bool:
        """Determines if the in-memory articles cache has expired or is empty."""
        if self.last_fetch_time is None:
            return True
        now = datetime.now(timezone.utc)
        elapsed = (now - self.last_fetch_time).total_seconds()
        return elapsed >= self.cache_duration_secs

    def update(self, articles: List[Article], source_statuses: Dict[str, SourceStatus]) -> None:
        """Updates the cache with fresh articles and tracks feed status."""
        self.current_articles = articles
        self.source_statuses = source_statuses
        self.last_fetch_time = datetime.now(timezone.utc)

    def clear(self) -> None:
        """Resets the state to empty."""
        self.current_articles = []
        self.last_fetch_time = None
        self.source_statuses = {}
