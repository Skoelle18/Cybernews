import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from cybernews.models import Article

logger = logging.getLogger("cybernews.storage.jsonl")

def load_articles(filepath: Path) -> List[Article]:
    """Loads all valid articles from the JSONL file.

    Skips and logs malformed lines. If file doesn't exist, returns empty list.
    """
    if not filepath.exists():
        logger.debug("JSONL archive does not exist at path: %s", filepath)
        return []

    articles = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    articles.append(Article.from_dict(data))
                except Exception as e:
                    logger.warning("Line %d in %s is malformed and was skipped: %s", idx, filepath, str(e))
    except Exception as e:
        logger.error("Failed to read JSONL file at %s: %s", filepath, str(e))

    return articles

def save_articles(articles: List[Article], filepath: Path) -> Tuple[int, int]:
    """Appends articles to the JSONL file, ignoring duplicates.

    Creates the file and directories if necessary.
    Returns:
        A tuple of (number of newly saved articles, number of skipped duplicates)
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Load existing articles to check for duplicates by ID
    existing = load_articles(filepath)
    existing_ids = {art.id for art in existing}

    saved_count = 0
    skipped_count = 0

    try:
        with open(filepath, "a", encoding="utf-8") as f:
            for article in articles:
                if article.id in existing_ids:
                    skipped_count += 1
                else:
                    line = json.dumps(article.to_dict())
                    f.write(line + "\n")
                    existing_ids.add(article.id)
                    saved_count += 1
    except Exception as e:
        logger.error("Failed to save articles to %s: %s", filepath, str(e))
        raise

    logger.info("Saved %d new articles, skipped %d duplicates", saved_count, skipped_count)
    return saved_count, skipped_count

def search_articles(query: str, filepath: Path) -> List[Article]:
    """Searches the JSONL archive case-insensitively across fields."""
    articles = load_articles(filepath)
    query_lower = query.lower()
    results = []
    for art in articles:
        if (
            query_lower in art.title.lower()
            or query_lower in art.summary.lower()
            or query_lower in art.source.lower()
            or query_lower in art.category.lower()
        ):
            results.append(art)
    return results

def filter_articles_by_category(category: str, filepath: Path) -> List[Article]:
    """Filters the JSONL archive by category case-insensitively."""
    articles = load_articles(filepath)
    category_lower = category.lower()
    return [art for art in articles if art.category.lower() == category_lower]

def get_archive_stats(filepath: Path) -> Dict[str, Any]:
    """Generates statistics for the persisted JSONL archive.

    Returns:
        A dictionary with keys: total, categories, sources, oldest_pub, latest_pub
    """
    articles = load_articles(filepath)
    total = len(articles)

    if total == 0:
        return {
            "total": 0,
            "categories": {},
            "sources": {},
            "oldest_pub": None,
            "latest_pub": None,
        }

    categories: Dict[str, int] = {}
    sources: Dict[str, int] = {}
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
    }
