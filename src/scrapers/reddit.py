"""Reddit scraper using PRAW (Python Reddit API Wrapper).

Requires Reddit API credentials. Create a Reddit app at:
https://www.reddit.com/prefs/apps

Set these environment variables:
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USER_AGENT (optional, defaults to "ai-news-automation/0.1")
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from src.models import NewsItem, Source
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "artificial",
    "ClaudeAI",
    "ChatGPT",
    "StableDiffusion",
]


class RedditScraper(BaseScraper):
    source = Source.REDDIT

    def scrape(self) -> list[NewsItem]:
        client_id = os.environ.get("REDDIT_CLIENT_ID", "")
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")

        if not client_id or not client_secret:
            logger.warning(
                "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set. "
                "Falling back to public JSON scraping."
            )
            return self._scrape_public()

        return self._scrape_praw(client_id, client_secret)

    def _scrape_praw(self, client_id: str, client_secret: str) -> list[NewsItem]:
        """Scrape using authenticated PRAW client."""
        import praw

        reddit_config = self.config.get("sources", {}).get("reddit", {})
        subreddits = reddit_config.get("subreddits", DEFAULT_SUBREDDITS)
        time_filter = reddit_config.get("time_filter", "day")
        limit = reddit_config.get("limit", 50)
        user_agent = os.environ.get("REDDIT_USER_AGENT", "ai-news-automation/0.1")

        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

        all_items: list[NewsItem] = []

        for sub_name in subreddits:
            try:
                subreddit = reddit.subreddit(sub_name)
                per_sub = max(limit // len(subreddits), 10)

                for post in subreddit.top(time_filter=time_filter, limit=per_sub):
                    item = NewsItem(
                        title=post.title,
                        url=post.url if not post.is_self else f"https://reddit.com{post.permalink}",
                        source=Source.REDDIT,
                        description=self._truncate(post.selftext, 500) if post.is_self else post.title,
                        score=post.score,
                        timestamp=datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
                        tags=[sub_name],
                        raw_data={
                            "subreddit": sub_name,
                            "num_comments": post.num_comments,
                            "author": str(post.author),
                            "is_self": post.is_self,
                            "permalink": post.permalink,
                        },
                    )
                    all_items.append(item)

                logger.info(f"[reddit/{sub_name}] Fetched {per_sub} posts")

            except Exception:
                logger.exception(f"[reddit/{sub_name}] Failed to scrape")
                continue

        all_items.sort(key=lambda x: x.score, reverse=True)
        return all_items[:limit]

    def _scrape_public(self) -> list[NewsItem]:
        """Fallback: scrape Reddit's public JSON endpoints (no auth needed, rate-limited)."""
        import requests
        import time

        reddit_config = self.config.get("sources", {}).get("reddit", {})
        subreddits = reddit_config.get("subreddits", DEFAULT_SUBREDDITS)
        limit = reddit_config.get("limit", 50)

        all_items: list[NewsItem] = []

        for sub_name in subreddits:
            try:
                resp = requests.get(
                    f"https://www.reddit.com/r/{sub_name}/top.json",
                    params={"t": "day", "limit": 15},
                    headers={"User-Agent": "ai-news-automation/0.1"},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()

                for child in data.get("data", {}).get("children", []):
                    post = child["data"]
                    is_self = post.get("is_self", False)

                    item = NewsItem(
                        title=post["title"],
                        url=post["url"] if not is_self else f"https://reddit.com{post['permalink']}",
                        source=Source.REDDIT,
                        description=self._truncate(post.get("selftext", ""), 500) if is_self else post["title"],
                        score=post.get("score", 0),
                        timestamp=datetime.fromtimestamp(post["created_utc"], tz=timezone.utc),
                        tags=[sub_name],
                        raw_data={
                            "subreddit": sub_name,
                            "num_comments": post.get("num_comments", 0),
                            "author": post.get("author", ""),
                            "is_self": is_self,
                            "permalink": post.get("permalink", ""),
                        },
                    )
                    all_items.append(item)

                logger.info(f"[reddit/{sub_name}] Fetched {len(data.get('data', {}).get('children', []))} posts (public)")

                # Rate limit: Reddit public API allows ~10 req/min
                time.sleep(2)

            except Exception:
                logger.exception(f"[reddit/{sub_name}] Public scrape failed")
                continue

        all_items.sort(key=lambda x: x.score, reverse=True)
        return all_items[:limit]

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len].rsplit(" ", 1)[0] + "..."
