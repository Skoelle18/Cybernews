import logging
from typing import List

from cybernews.models import Article

logger = logging.getLogger("cybernews.processing.deduplicate")

def deduplicate_articles(articles: List[Article]) -> List[Article]:
    """Deduplicates a list of Articles by their ID, maintaining original order.

    Keeps the first occurrence of each unique ID.
    """
    seen_ids = set()
    unique_articles = []
    
    for article in articles:
        if article.id not in seen_ids:
            seen_ids.add(article.id)
            unique_articles.append(article)
        else:
            logger.debug("Deduplicated article skipped: %s ('%s')", article.id, article.title)
            
    duplicates_removed = len(articles) - len(unique_articles)
    if duplicates_removed > 0:
        logger.info("Deduplicated in-memory pipeline: removed %d articles", duplicates_removed)
        
    return unique_articles
