from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

@dataclass
class Article:
    """Represents a single cyber news article."""
    id: str
    title: str
    url: str
    summary: str
    source: str
    category: str
    published_at: datetime  # Timezone-aware UTC datetime

    def to_dict(self) -> dict:
        """Serializes the Article into a JSON-compatible dictionary."""
        d = asdict(self)
        d["published_at"] = self.published_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        """Deserializes a dictionary into an Article dataclass."""
        published_at = datetime.fromisoformat(d["published_at"])
        return cls(
            id=d["id"],
            title=d["title"],
            url=d["url"],
            summary=d["summary"],
            source=d["source"],
            category=d["category"],
            published_at=published_at,
        )

@dataclass
class SourceStatus:
    """Tracks the collection status of an RSS source."""
    name: str
    url: str
    success: bool
    articles_count: int
    error_message: Optional[str] = None
