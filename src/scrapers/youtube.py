"""YouTube scraper for AI channels using yt-dlp (no API key needed).

Uses yt-dlp's extract_flat mode to get video metadata without downloading.
Filters for videos published in the last 48 hours.
"""

from __future__ import annotations

import logging
import subprocess
import json
from datetime import datetime, timedelta, timezone

from src.models import NewsItem, Source
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DEFAULT_CHANNELS = [
    # AI news and tutorials
    "https://www.youtube.com/@AllAboutAI",
    "https://www.youtube.com/@AIJasonZ",
    "https://www.youtube.com/@maboroshi_AI",
    "https://www.youtube.com/@MattVidPro",
    "https://www.youtube.com/@WorldofAI",
    "https://www.youtube.com/@TwoMinutePapers",
    # AI dev / engineering
    "https://www.youtube.com/@ArjanCodes",
    "https://www.youtube.com/@jaboroham",  # Fireship
    "https://www.youtube.com/@YannicKilcher",
    "https://www.youtube.com/@sentdex",
]


class YouTubeScraper(BaseScraper):
    source = Source.YOUTUBE

    def scrape(self) -> list[NewsItem]:
        yt_config = self.config.get("sources", {}).get("youtube", {})
        channels = yt_config.get("channels", DEFAULT_CHANNELS)
        max_per_channel = yt_config.get("max_per_channel", 5)

        all_items: list[NewsItem] = []

        for channel_url in channels:
            try:
                items = self._scrape_channel(channel_url, max_per_channel)
                all_items.extend(items)
                logger.info(f"[youtube] {channel_url}: {len(items)} recent videos")
            except Exception:
                logger.exception(f"[youtube] Failed to scrape: {channel_url}")

        # Sort by recency
        all_items.sort(key=lambda x: x.timestamp, reverse=True)
        return all_items

    def _scrape_channel(self, channel_url: str, max_videos: int) -> list[NewsItem]:
        """Scrape recent videos from a YouTube channel using yt-dlp."""
        # Extract channel name from URL for fallback
        channel_name = channel_url.rstrip("/").split("/")[-1].lstrip("@")

        try:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--flat-playlist",
                    "--dump-json",
                    "--playlist-end", str(max_videos),
                    "--no-warnings",
                    f"{channel_url}/videos",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            logger.warning("yt-dlp not found. Install with: pip install yt-dlp")
            return []
        except subprocess.TimeoutExpired:
            logger.warning(f"yt-dlp timed out for {channel_url}")
            return []

        if result.returncode != 0:
            logger.debug(f"yt-dlp error for {channel_url}: {result.stderr[:200]}")
            return []

        items = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                video = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Parse upload date
            upload_date = video.get("upload_date", "")  # YYYYMMDD format
            if upload_date:
                try:
                    ts = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    ts = datetime.now(timezone.utc)
            else:
                ts = datetime.now(timezone.utc)

            # Skip videos older than 48 hours
            if ts < cutoff:
                continue

            video_id = video.get("id", "")
            title = video.get("title", "")
            channel = video.get("channel") or video.get("uploader") or channel_name
            duration = video.get("duration") or 0

            # Skip shorts (< 60 seconds)
            if duration and duration < 60:
                continue

            url = f"https://www.youtube.com/watch?v={video_id}" if video_id else video.get("url", "")

            items.append(
                NewsItem(
                    title=f"[{channel}] {title}",
                    url=url,
                    source=Source.YOUTUBE,
                    description=video.get("description", "")[:500] if video.get("description") else title,
                    score=video.get("view_count", 0) or 0,
                    timestamp=ts,
                    tags=[channel] if channel else [],
                    raw_data={
                        "channel": channel,
                        "video_id": video_id,
                        "duration": duration,
                        "view_count": video.get("view_count", 0),
                    },
                )
            )

        return items
