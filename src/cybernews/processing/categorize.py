import re
from typing import List

from cybernews.models import Article

# Priority order for categorization: top elements override lower ones
CATEGORIES_PRIORITY = [
    "ransomware",
    "data_breach",
    "malware",
    "vulnerability",
    "exploit",
    "apt",
    "phishing",
    "security_research",
]

CATEGORY_KEYWORDS = {
    "ransomware": ["ransomware"],
    "data_breach": ["data breach", "leaked data", "database leak"],
    "malware": ["trojan", "malware", "backdoor", "spyware", "rootkit", "worm", "botnet"],
    "vulnerability": ["cve", "zero-day", "vulnerability", "vulnerabilities"],
    "exploit": ["exploit", "rce", "remote code execution", "proof of concept", "poc"],
    "apt": ["apt", "advanced persistent threat", "nation-state"],
    "phishing": ["phishing", "credential theft", "credential harvesting", "spear-phishing"],
    "security_research": ["researchers discovered", "security researchers", "research team"],
}

def categorize_article(article: Article) -> Article:
    """Categorizes a single Article based on keyword matches in its title and summary.

    Updates the category field in place.
    """
    text_to_check = f"{article.title} {article.summary}".lower()

    for category in CATEGORIES_PRIORITY:
        keywords = CATEGORY_KEYWORDS[category]
        for keyword in keywords:
            # Match using word boundaries to prevent substring collisions (e.g. 'capturing' matching 'apt')
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, text_to_check):
                article.category = category
                return article

    # Fallback category if no keywords match
    article.category = "general"
    return article

def categorize_articles(articles: List[Article]) -> List[Article]:
    """Categorizes a list of Articles in place, returning the list."""
    for article in articles:
        categorize_article(article)
    return articles
