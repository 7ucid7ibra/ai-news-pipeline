"""RSS/Atom feed scraper for AI newsletters and blogs.

Uses feedparser — no authentication required.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import mktime

import feedparser

from src.models import NewsItem, Source
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = [
    # Major tech publications with AI coverage
    {"name": "MIT Technology Review - AI", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"},
    {"name": "The Verge - AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "VentureBeat - AI", "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "TechCrunch - AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    # AI lab blogs
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml"},
    {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/"},
    {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml"},
    # Developer-focused
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/"},
]


class RSSFeedScraper(BaseScraper):
    source = Source.RSS

    def scrape(self) -> list[NewsItem]:
        rss_config = self.config.get("sources", {}).get("rss", {})
        feeds = rss_config.get("feeds", DEFAULT_FEEDS)

        all_items: list[NewsItem] = []

        for feed_info in feeds:
            name = feed_info["name"]
            url = feed_info["url"]

            try:
                items = self._parse_feed(name, url)
                all_items.extend(items)
                logger.info(f"[rss/{name}] Fetched {len(items)} entries")
            except Exception:
                logger.exception(f"[rss/{name}] Failed to parse feed")

        # Dedup by URL
        seen: set[str] = set()
        unique = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)

        # Sort by timestamp (most recent first)
        unique.sort(key=lambda x: x.timestamp, reverse=True)
        return unique

    def _parse_feed(self, feed_name: str, feed_url: str) -> list[NewsItem]:
        """Parse a single RSS/Atom feed."""
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            if not feed.entries:
                logger.warning(f"[rss/{feed_name}] Feed parse error (no entries): {feed.bozo_exception}")
                return []
            logger.debug(f"[rss/{feed_name}] Feed had parse warning but got {len(feed.entries)} entries: {feed.bozo_exception}")

        items = []
        now = datetime.now(timezone.utc)

        for entry in feed.entries[:20]:  # Cap per feed
            # Parse timestamp
            ts = now
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                ts = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                ts = datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)

            # Skip entries older than 48 hours
            age_hours = (now - ts).total_seconds() / 3600
            if age_hours > 48:
                continue

            # Extract description (strip HTML roughly)
            description = entry.get("summary", entry.get("description", ""))
            description = self._strip_html(description)[:500]

            title = entry.get("title", "")
            link = entry.get("link", "")

            items.append(
                NewsItem(
                    title=title,
                    url=link,
                    source=Source.RSS,
                    description=description,
                    score=0,  # RSS feeds don't have scores
                    timestamp=ts,
                    tags=[feed_name],
                    raw_data={
                        "feed_name": feed_name,
                        "feed_url": feed_url,
                        "author": entry.get("author", ""),
                    },
                )
            )

        return items

    @staticmethod
    def _strip_html(text: str) -> str:
        """Rough HTML tag removal."""
        import re
        clean = re.sub(r"<[^>]+>", " ", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean
