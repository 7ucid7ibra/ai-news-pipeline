"""HackerNews scraper using the Algolia API (free, no auth required)."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

import requests

from src.models import NewsItem, Source
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
HN_SEARCH_BY_DATE_URL = "https://hn.algolia.com/api/v1/search_by_date"
HN_ITEM_URL = "https://news.ycombinator.com/item?id="

# Default AI-related keywords — use word boundaries to avoid false positives
DEFAULT_AI_KEYWORDS = [
    "AI", "LLM", "GPT", "Claude", "machine learning", "deep learning",
    "neural network", "transformer model", "diffusion model", "AI agent",
    "RAG", "fine-tun", "embedding", "vector database", "MCP",
    "model context protocol", "Anthropic", "OpenAI", "Gemini", "Mistral",
    "Llama", "Stable Diffusion", "Cursor", "Copilot", "ChatGPT",
    "large language model", "artificial intelligence",
]

# Words that match "AI" as a substring but aren't about AI
FALSE_POSITIVE_PATTERNS = [
    r"\bairfoil\b", r"\bfair\b", r"\bmail\b", r"\brain\b",
    r"\bpaint\b", r"\bmaintain\b", r"\bcontain\b",
]


class HackerNewsScraper(BaseScraper):
    source = Source.HACKERNEWS

    def scrape(self) -> list[NewsItem]:
        hn_config = self.config.get("sources", {}).get("hackernews", {})
        min_score = hn_config.get("min_score", 10)
        limit = hn_config.get("limit", 30)
        keywords = hn_config.get("ai_keywords", DEFAULT_AI_KEYWORDS)

        # Only fetch stories from the last 24 hours
        since_ts = int(time.time()) - 86400

        all_items: list[NewsItem] = []

        for keyword in keywords:
            items = self._search(keyword, min_score, since_ts)
            all_items.extend(items)

            if len(all_items) >= limit * 3:  # fetch extra, dedup later
                break

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique: list[NewsItem] = []
        for item in all_items:
            if item.url not in seen_urls and self._is_relevant(item.title):
                seen_urls.add(item.url)
                unique.append(item)

        # Sort by score descending, take top N
        unique.sort(key=lambda x: x.score, reverse=True)
        return unique[:limit]

    def _search(self, query: str, min_score: int, since_ts: int) -> list[NewsItem]:
        """Search HN Algolia API for a single query, filtered to recent stories."""
        try:
            resp = requests.get(
                HN_SEARCH_URL,
                params={
                    "query": query,
                    "tags": "story",
                    "numericFilters": f"points>{min_score},created_at_i>{since_ts}",
                    "hitsPerPage": 20,
                },
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception(f"HN search failed for query: {query}")
            return []

        hits = resp.json().get("hits", [])
        items = []

        for hit in hits:
            url = hit.get("url") or f"{HN_ITEM_URL}{hit['objectID']}"
            created = hit.get("created_at", "")
            try:
                ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                ts = datetime.now(timezone.utc)

            items.append(
                NewsItem(
                    title=hit.get("title", ""),
                    url=url,
                    source=Source.HACKERNEWS,
                    description=hit.get("title", ""),
                    score=hit.get("points", 0),
                    timestamp=ts,
                    tags=self._extract_tags(hit),
                    raw_data={
                        "hn_id": hit.get("objectID"),
                        "num_comments": hit.get("num_comments", 0),
                        "author": hit.get("author", ""),
                    },
                )
            )

        return items

    def _extract_tags(self, hit: dict) -> list[str]:
        """Extract relevant tags from a HN story."""
        tags = []
        title = (hit.get("title") or "").lower()
        for kw in DEFAULT_AI_KEYWORDS:
            # Use word boundary matching for short keywords
            if len(kw) <= 3:
                if re.search(rf"\b{re.escape(kw.lower())}\b", title):
                    tags.append(kw)
            elif kw.lower() in title:
                tags.append(kw)
        return tags

    def _is_relevant(self, title: str) -> bool:
        """Filter out false positives where 'AI' matches as a substring."""
        title_lower = title.lower()
        for pattern in FALSE_POSITIVE_PATTERNS:
            if re.search(pattern, title_lower) and not re.search(r"\bai\b", title_lower):
                return False
        return True
