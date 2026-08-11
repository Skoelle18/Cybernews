import calendar
from datetime import datetime, timezone
import email.utils
import hashlib
import html
import logging
import re
from typing import Any, Dict, List, Optional

from cybernews.models import Article

logger = logging.getLogger("cybernews.processing.normalize")

class NormalizationError(Exception):
    """Raised when an RSS entry cannot be normalized due to missing/invalid required data."""
    pass

def clean_html(text: Optional[str]) -> str:
    """Removes HTML tags and decodes entities from a string."""
    if not text:
        return ""
    # Strip HTML tags
    cleanr = re.compile("<.*?>")
    cleantext = re.sub(cleanr, "", text)
    # Convert HTML entities like &amp;, &lt;, &#39;
    return html.unescape(cleantext).strip()

def parse_date(entry: Dict[str, Any]) -> datetime:
    """Attempts to extract and parse publication date from an RSS entry.

    Returns:
        A timezone-aware UTC datetime.
        
    Raises:
        NormalizationError if date is missing or invalid.
    """
    # feedparser populates published_parsed or updated_parsed
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_time:
        try:
            ts = calendar.timegm(parsed_time)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError) as e:
            raise NormalizationError(f"Invalid publication date parsed struct: {e}")
            
    # Try raw strings fallback
    for date_key in ("published", "updated", "pubDate"):
        val = entry.get(date_key)
        if val:
            if isinstance(val, str):
                try:
                    # Parse RFC 822 format (e.g. 'Mon, 20 Oct 2026 12:00:00 GMT')
                    dt = email.utils.parsedate_to_datetime(val)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc)
                except Exception:
                    try:
                        dt = datetime.fromisoformat(val)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt.astimezone(timezone.utc)
                    except Exception:
                        pass
            elif hasattr(val, "tm_year"):
                try:
                    ts = calendar.timegm(val)
                    return datetime.fromtimestamp(ts, tz=timezone.utc)
                except Exception:
                    pass

    raise NormalizationError("Missing or invalid publication date")

def normalize_entry(entry: Dict[str, Any], source_name: str) -> Article:
    """Normalizes a raw feedparser entry dictionary into an Article dataclass.

    Args:
        entry: Raw dictionary of RSS entry from feedparser.
        source_name: Name of the feed source.

    Returns:
        A validated Article object.

    Raises:
        NormalizationError if title or link is missing/empty, or date parsing fails.
    """
    title = entry.get("title")
    if not title or not title.strip():
        raise NormalizationError("Missing title")

    url = entry.get("link")
    if not url or not url.strip():
        raise NormalizationError("Missing URL")

    title = title.strip()
    url = url.strip()

    summary = entry.get("summary") or entry.get("description") or ""
    summary = clean_html(summary)

    published_at = parse_date(entry)

    # Deterministic ID based on SHA-256 of URL
    article_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]

    return Article(
        id=article_id,
        title=title,
        url=url,
        summary=summary,
        source=source_name,
        category="general",  # Default category, set later by categorizer
        published_at=published_at
    )

def normalize_articles(entries: List[Dict[str, Any]], source_name: str) -> List[Article]:
    """Converts raw RSS entries into normalized Article objects, skipping invalid ones."""
    articles = []
    for entry in entries:
        try:
            article = normalize_entry(entry, source_name)
            articles.append(article)
        except NormalizationError as ne:
            logger.warning("Skipping entry from source '%s': %s", source_name, str(ne))
        except Exception as e:
            logger.error("Unexpected error normalizing entry from source '%s': %s", source_name, str(e))
    return articles
