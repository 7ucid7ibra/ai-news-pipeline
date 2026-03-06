"""Aggregator: deduplicates and normalizes NewsItems across sources."""

from __future__ import annotations

import logging

from rapidfuzz import fuzz

from src.models import NewsItem

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 75  # fuzzy match score to consider items as duplicates


def aggregate(items: list[NewsItem]) -> list[NewsItem]:
    """Deduplicate items across sources and normalize scores."""
    if not items:
        return []

    # Group duplicates by fuzzy title matching
    groups: list[list[NewsItem]] = []

    for item in items:
        merged = False
        for group in groups:
            if _is_duplicate(item, group[0]):
                group.append(item)
                merged = True
                break
        if not merged:
            groups.append([item])

    # Merge each group into a single representative item
    merged_items: list[NewsItem] = []
    for group in groups:
        representative = _merge_group(group)
        merged_items.append(representative)

    # Normalize scores to 0-100
    if merged_items:
        max_score = max(item.score for item in merged_items) or 1
        for item in merged_items:
            item.normalized_score = round((item.score / max_score) * 100, 1)

    # Sort by normalized score (boosted by cross-posting)
    merged_items.sort(
        key=lambda x: x.normalized_score * (1 + 0.25 * (x.cross_posted - 1)),
        reverse=True,
    )

    logger.info(
        f"Aggregated {len(items)} items into {len(merged_items)} unique items"
    )
    return merged_items


def _is_duplicate(a: NewsItem, b: NewsItem) -> bool:
    """Check if two items refer to the same thing."""
    # Exact URL match
    if a.url == b.url:
        return True
    # Fuzzy title match
    return fuzz.token_sort_ratio(a.title, b.title) >= SIMILARITY_THRESHOLD


def _merge_group(group: list[NewsItem]) -> NewsItem:
    """Merge a group of duplicate items into one representative."""
    # Pick the item with the highest score as the representative
    best = max(group, key=lambda x: x.score)
    best.cross_posted = len(group)

    # Merge tags from all duplicates
    all_tags = set()
    for item in group:
        all_tags.update(item.tags)
    best.tags = sorted(all_tags)

    # Sum scores across sources for combined weight
    best.score = sum(item.score for item in group)

    # Note which sources mentioned this
    sources = {item.source.value for item in group}
    best.raw_data["all_sources"] = sorted(sources)

    return best
