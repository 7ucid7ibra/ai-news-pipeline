"""Base scraper interface."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from src.models import NewsItem, Source

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"


class BaseScraper(ABC):
    """Abstract base for all news scrapers."""

    source: Source

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def scrape(self) -> list[NewsItem]:
        """Fetch news items from this source. Must be implemented by subclasses."""
        ...

    def scrape_with_cache(self, today: date | None = None) -> list[NewsItem]:
        """Scrape with filesystem caching to avoid re-fetching."""
        today = today or date.today()
        cache_dir = DATA_DIR / "raw" / str(today)
        cache_file = cache_dir / f"{self.source.value}.json"

        if cache_file.exists():
            logger.info(f"[{self.source.value}] Using cached data from {cache_file}")
            data = json.loads(cache_file.read_text())
            return [self._from_cache(item) for item in data]

        logger.info(f"[{self.source.value}] Scraping fresh data...")
        try:
            items = self.scrape()
        except Exception:
            logger.exception(f"[{self.source.value}] Scrape failed")
            return []

        # Cache results
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps([item.to_dict() for item in items], indent=2)
        )
        logger.info(f"[{self.source.value}] Scraped {len(items)} items, cached to {cache_file}")
        return items

    def _from_cache(self, data: dict) -> NewsItem:
        """Reconstruct a NewsItem from cached JSON."""
        from datetime import datetime

        return NewsItem(
            title=data["title"],
            url=data["url"],
            source=Source(data["source"]),
            description=data["description"],
            score=data.get("score", 0),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            tags=data.get("tags", []),
        )
