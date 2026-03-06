"""GitHub trending scraper using the GitHub API via gh CLI and REST API.

No additional auth needed — uses the gh CLI which is already authenticated.
Falls back to the GitHub REST API (unauthenticated) if gh is unavailable.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone

import requests

from src.models import NewsItem, Source
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

AI_TOPICS = [
    "llm", "large-language-model", "ai", "machine-learning",
    "deep-learning", "gpt", "claude", "transformer", "diffusion",
    "agent", "rag", "embedding", "vector-database", "mcp",
    "model-context-protocol", "fine-tuning", "nlp",
]


class GitHubTrendingScraper(BaseScraper):
    source = Source.GITHUB

    def scrape(self) -> list[NewsItem]:
        gh_config = self.config.get("sources", {}).get("github", {})
        languages = gh_config.get("languages", ["python", "typescript", "rust"])

        # Try gh CLI first, fall back to REST API
        items = self._scrape_via_api(languages)
        return items

    def _scrape_via_api(self, languages: list[str]) -> list[NewsItem]:
        """Search GitHub API for newly created AI repos gaining traction."""
        # Focus on repos created in the last 30 days with meaningful stars
        created_since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        all_items: list[NewsItem] = []

        for lang in languages:
            query = self._build_query(lang, created_since)
            items = self._search_repos(query)
            all_items.extend(items)

        # General AI repos created recently
        general_query = f"topic:ai created:>{created_since} stars:>50"
        all_items.extend(self._search_repos(general_query))

        # Also catch repos with "llm" or "mcp" in the name (very recent tools)
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        for term in ["llm", "mcp", "ai-agent", "claude"]:
            fresh_query = f"{term} in:name,description created:>{week_ago} stars:>5"
            all_items.extend(self._search_repos(fresh_query))

        # Dedup by URL
        seen: set[str] = set()
        unique = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)

        unique.sort(key=lambda x: x.score, reverse=True)
        return unique[:30]

    def _build_query(self, language: str, created_since: str) -> str:
        """Build a GitHub search query for newly created AI repos."""
        ai_terms = " OR ".join(f'"{t}"' for t in AI_TOPICS[:5])
        return f"({ai_terms}) language:{language} created:>{created_since} stars:>10"

    def _search_repos(self, query: str) -> list[NewsItem]:
        """Execute a GitHub repo search."""
        # Try gh CLI first
        items = self._search_via_gh(query)
        if items is not None:
            return items

        # Fall back to REST API
        return self._search_via_rest(query)

    def _search_via_gh(self, query: str) -> list[NewsItem] | None:
        """Search using gh CLI (already authenticated)."""
        try:
            result = subprocess.run(
                [
                    "gh", "api", "search/repositories",
                    "-X", "GET",
                    "-f", f"q={query}",
                    "-f", "sort=stars",
                    "-f", "order=desc",
                    "-f", "per_page=20",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.debug(f"gh CLI failed: {result.stderr}")
                return None

            data = json.loads(result.stdout)
            return self._parse_repos(data.get("items", []))

        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("gh CLI not available or timed out")
            return None

    def _search_via_rest(self, query: str) -> list[NewsItem]:
        """Search using unauthenticated GitHub REST API."""
        try:
            resp = requests.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 20,
                },
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_repos(data.get("items", []))

        except requests.RequestException:
            logger.exception(f"GitHub REST API search failed for: {query}")
            return []

    def _parse_repos(self, repos: list[dict]) -> list[NewsItem]:
        """Parse GitHub API repo results into NewsItems."""
        items = []

        for repo in repos:
            created = repo.get("created_at", "")
            try:
                ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                ts = datetime.now(timezone.utc)

            topics = repo.get("topics", [])
            language = repo.get("language", "")
            tags = [t for t in topics if any(ai in t.lower() for ai in AI_TOPICS)]
            if language:
                tags.append(language.lower())

            description = repo.get("description") or ""

            items.append(
                NewsItem(
                    title=f"{repo['full_name']}: {description[:100]}",
                    url=repo["html_url"],
                    source=Source.GITHUB,
                    description=description,
                    score=repo.get("stargazers_count", 0),
                    timestamp=ts,
                    tags=tags,
                    raw_data={
                        "full_name": repo["full_name"],
                        "stars": repo.get("stargazers_count", 0),
                        "forks": repo.get("forks_count", 0),
                        "language": language,
                        "topics": topics,
                        "open_issues": repo.get("open_issues_count", 0),
                        "updated_at": repo.get("updated_at", ""),
                    },
                )
            )

        return items
