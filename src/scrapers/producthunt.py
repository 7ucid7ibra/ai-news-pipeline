"""Product Hunt scraper for AI product launches.

Uses PH's RSS feed with AI keyword filtering.
Optionally uses GraphQL API if PH_ACCESS_TOKEN is set.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from time import mktime

import feedparser
import requests

from src.models import NewsItem, Source
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

AI_KEYWORDS = [
    "ai", "llm", "gpt", "machine learning", "artificial intelligence",
    "neural", "model", "agent", "automation", "chatbot", "copilot",
    "deep learning", "generative", "diffusion", "embedding", "vector",
    "claude", "openai", "anthropic", "gemini",
]


class ProductHuntScraper(BaseScraper):
    source = Source.PRODUCTHUNT

    def scrape(self) -> list[NewsItem]:
        token = os.environ.get("PH_ACCESS_TOKEN", "")
        if token:
            items = self._scrape_api(token)
            if items:
                return items

        return self._scrape_rss()

    def _scrape_rss(self) -> list[NewsItem]:
        """Scrape PH via their RSS feed, filtering for AI products."""
        items: list[NewsItem] = []

        feed = feedparser.parse("https://www.producthunt.com/feed")

        if not feed.entries:
            logger.warning("[producthunt] RSS feed returned no entries")
            return []

        for entry in feed.entries:
            ts = datetime.now(timezone.utc)
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                ts = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            combined = f"{title} {summary}".lower()

            if not any(kw in combined for kw in AI_KEYWORDS):
                continue

            items.append(
                NewsItem(
                    title=title,
                    url=entry.get("link", ""),
                    source=Source.PRODUCTHUNT,
                    description=self._strip_html(summary)[:500],
                    score=0,  # RSS doesn't include vote counts
                    timestamp=ts,
                    tags=self._extract_tags(combined),
                    raw_data={"method": "rss"},
                )
            )

        logger.info(f"[producthunt/rss] Found {len(items)} AI products from {len(feed.entries)} total")
        return items

    def _scrape_api(self, token: str) -> list[NewsItem]:
        """Scrape using Product Hunt GraphQL API (requires access token)."""
        query = """
        query {
            posts(first: 30, order: VOTES) {
                edges {
                    node {
                        name
                        tagline
                        url
                        website
                        votesCount
                        createdAt
                        topics {
                            edges {
                                node { name slug }
                            }
                        }
                    }
                }
            }
        }
        """

        try:
            resp = requests.post(
                "https://api.producthunt.com/v2/api/graphql",
                json={"query": query},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            items = []
            edges = data.get("data", {}).get("posts", {}).get("edges", [])
            for edge in edges:
                node = edge["node"]
                topic_names = [e["node"]["name"] for e in node.get("topics", {}).get("edges", [])]

                # Filter for AI-related topics
                combined = f"{node.get('name', '')} {node.get('tagline', '')} {' '.join(topic_names)}".lower()
                if not any(kw in combined for kw in AI_KEYWORDS):
                    continue

                ts = datetime.now(timezone.utc)
                if node.get("createdAt"):
                    try:
                        ts = datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00"))
                    except ValueError:
                        pass

                items.append(
                    NewsItem(
                        title=node.get("name", ""),
                        url=node.get("website") or node.get("url", ""),
                        source=Source.PRODUCTHUNT,
                        description=node.get("tagline", ""),
                        score=node.get("votesCount", 0),
                        timestamp=ts,
                        tags=topic_names,
                        raw_data={"method": "api", "ph_url": node.get("url", "")},
                    )
                )

            logger.info(f"[producthunt/api] Found {len(items)} AI products")
            return items

        except Exception:
            logger.exception("[producthunt/api] GraphQL API failed")
            return []

    def _extract_tags(self, text: str) -> list[str]:
        return [kw for kw in AI_KEYWORDS[:10] if kw in text]

    @staticmethod
    def _strip_html(text: str) -> str:
        import re
        clean = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", clean).strip()
