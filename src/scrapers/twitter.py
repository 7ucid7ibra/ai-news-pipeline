"""Twitter/X scraper for AI accounts.

Strategy (in order of reliability):
1. Nitter RSS feeds (public Nitter instances, no auth)
2. RSS.app or similar third-party Twitter-to-RSS services
3. Direct X API (if TWITTER_BEARER_TOKEN is set)

Note: X/Twitter aggressively blocks scraping. Nitter instances go up and
down frequently. This scraper is best-effort and may return 0 items.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
import requests

from src.models import NewsItem, Source
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Key AI accounts to follow
DEFAULT_ACCOUNTS = [
    "AnthropicAI",
    "OpenAI",
    "GoogleDeepMind",
    "xaboroham",       # Fireship
    "kaboroham",       # Andrej Karpathy
    "ylecun",
    "ClaudeAI",
    "huggingface",
    "LangChainAI",
    "siaboroham",      # Simon Willison
]

# Public Nitter instances (these change frequently — update as needed)
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.cz",
]


class TwitterScraper(BaseScraper):
    source = Source.TWITTER

    def scrape(self) -> list[NewsItem]:
        tw_config = self.config.get("sources", {}).get("twitter", {})
        accounts = tw_config.get("accounts", DEFAULT_ACCOUNTS)

        # Try X API first if token is available
        bearer = os.environ.get("TWITTER_BEARER_TOKEN", "")
        if bearer:
            items = self._scrape_api(accounts, bearer)
            if items:
                return items

        # Try Nitter RSS
        items = self._scrape_nitter(accounts)
        if items:
            return items

        logger.warning(
            "[twitter] All scraping methods failed. "
            "Set TWITTER_BEARER_TOKEN or check Nitter instance availability."
        )
        return []

    def _scrape_nitter(self, accounts: list[str]) -> list[NewsItem]:
        """Scrape via Nitter RSS feeds."""
        all_items: list[NewsItem] = []
        working_instance = None

        for instance in NITTER_INSTANCES:
            # Test if instance is alive
            try:
                resp = requests.get(f"{instance}/", timeout=5)
                if resp.status_code == 200:
                    working_instance = instance
                    break
            except requests.RequestException:
                continue

        if not working_instance:
            logger.warning("[twitter/nitter] No working Nitter instances found")
            return []

        logger.info(f"[twitter/nitter] Using instance: {working_instance}")
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        for account in accounts:
            try:
                feed_url = f"{working_instance}/{account}/rss"
                feed = feedparser.parse(feed_url)

                if not feed.entries:
                    continue

                for entry in feed.entries[:10]:
                    ts = datetime.now(timezone.utc)
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        ts = datetime.fromtimestamp(
                            mktime(entry.published_parsed), tz=timezone.utc
                        )

                    if ts < cutoff:
                        continue

                    title = entry.get("title", "")[:280]
                    link = entry.get("link", "")
                    # Convert Nitter link back to Twitter
                    if working_instance in link:
                        link = link.replace(working_instance, "https://x.com")

                    all_items.append(
                        NewsItem(
                            title=f"@{account}: {title}",
                            url=link,
                            source=Source.TWITTER,
                            description=title,
                            score=0,  # Can't get like counts from RSS
                            timestamp=ts,
                            tags=[account],
                            raw_data={
                                "account": account,
                                "method": "nitter",
                            },
                        )
                    )

                logger.debug(f"[twitter/nitter] @{account}: got entries")

            except Exception:
                logger.debug(f"[twitter/nitter] Failed for @{account}")
                continue

        logger.info(f"[twitter/nitter] Got {len(all_items)} tweets from {len(accounts)} accounts")
        return all_items

    def _scrape_api(self, accounts: list[str], bearer: str) -> list[NewsItem]:
        """Scrape using official X API v2 (requires Bearer token)."""
        all_items: list[NewsItem] = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        headers = {
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        }

        for account in accounts:
            try:
                # Get user ID
                user_resp = requests.get(
                    f"https://api.twitter.com/2/users/by/username/{account}",
                    headers=headers,
                    timeout=10,
                )
                if user_resp.status_code != 200:
                    continue

                user_id = user_resp.json().get("data", {}).get("id")
                if not user_id:
                    continue

                # Get recent tweets
                tweets_resp = requests.get(
                    f"https://api.twitter.com/2/users/{user_id}/tweets",
                    params={
                        "max_results": 10,
                        "tweet.fields": "created_at,public_metrics",
                        "start_time": cutoff.isoformat(),
                    },
                    headers=headers,
                    timeout=10,
                )
                if tweets_resp.status_code != 200:
                    continue

                tweets = tweets_resp.json().get("data", [])
                for tweet in tweets:
                    ts = datetime.now(timezone.utc)
                    if tweet.get("created_at"):
                        try:
                            ts = datetime.fromisoformat(
                                tweet["created_at"].replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass

                    metrics = tweet.get("public_metrics", {})
                    text = tweet.get("text", "")

                    all_items.append(
                        NewsItem(
                            title=f"@{account}: {text[:200]}",
                            url=f"https://x.com/{account}/status/{tweet['id']}",
                            source=Source.TWITTER,
                            description=text,
                            score=metrics.get("like_count", 0) + metrics.get("retweet_count", 0),
                            timestamp=ts,
                            tags=[account],
                            raw_data={
                                "account": account,
                                "method": "api",
                                "metrics": metrics,
                            },
                        )
                    )

            except Exception:
                logger.debug(f"[twitter/api] Failed for @{account}")
                continue

        logger.info(f"[twitter/api] Got {len(all_items)} tweets")
        return all_items
