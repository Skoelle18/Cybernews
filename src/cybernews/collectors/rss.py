import logging
import urllib.request
from typing import List, Tuple
import feedparser

from cybernews.models import SourceStatus

logger = logging.getLogger("cybernews.collectors.rss")

def fetch_feed(
    name: str,
    url: str,
    timeout: float = 10.0,
    retries: int = 2
) -> Tuple[List[dict], SourceStatus]:
    """Fetches and parses a single RSS feed.

    Args:
        name: Name of the feed source (e.g., 'The Hacker News')
        url: The RSS feed URL
        timeout: Socket timeout in seconds
        retries: Number of retry attempts on network failure

    Returns:
        A tuple of (list of parsed entries, SourceStatus object)
    """
    logger.info("Fetching feed: %s (%s)", name, url)
    headers = {
        # Some feeds block the default python-urllib User-Agent
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CyberNews/0.1.0"
    }
    req = urllib.request.Request(url, headers=headers)
    
    last_error = None
    for attempt in range(retries + 1):
        try:
            # Nosec: url is configured and from a trusted set
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw_data = response.read()
                parsed = feedparser.parse(raw_data)
                
                # Check for parsing anomalies
                if parsed.bozo:
                    exception_str = str(parsed.bozo_exception)
                    logger.warning("Feed '%s' parsed with warning: %s", name, exception_str)
                    # If we parsed zero entries and bozo is set, treat as error
                    if not parsed.entries:
                        raise ValueError(f"Malformed feed parsing error: {exception_str}")
                
                count = len(parsed.entries)
                logger.info("Successfully fetched %d entries from '%s'", count, name)
                
                return parsed.entries, SourceStatus(
                    name=name,
                    url=url,
                    success=True,
                    articles_count=count,
                    error_message=None
                )
        except Exception as e:
            last_error = e
            logger.warning("Attempt %d failed for '%s': %s", attempt + 1, name, str(e))
            
    # All attempts failed
    error_msg = str(last_error)
    logger.error("Failed to fetch '%s' after %d retries. Error: %s", name, retries, error_msg)
    return [], SourceStatus(
        name=name,
        url=url,
        success=False,
        articles_count=0,
        error_message=error_msg
    )
