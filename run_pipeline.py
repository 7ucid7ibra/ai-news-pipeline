#!/usr/bin/env python3
"""AI News Automation Pipeline — Main entry point.

Usage:
    python run_pipeline.py                          # Full pipeline
    python run_pipeline.py --dry-run                # Scrape + rank only
    python run_pipeline.py --digest                 # Scrape + rank + generate digest (no testing)
    python run_pipeline.py --sources hackernews     # Single source
    python run_pipeline.py --stage scrape           # Run one stage
    python run_pipeline.py --date 2026-03-06        # Specific date
    python run_pipeline.py --llm                    # Use LLM for ranking (auto-detects provider)
    python run_pipeline.py --llm --provider ollama  # Use Ollama specifically
    python run_pipeline.py --llm --provider anthropic --model claude-sonnet-4-6
    python run_pipeline.py --max-test 3             # Test only top 3 tools
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from src.agent.evaluator import evaluate, generate_report
from src.agent.tester import test_tools as agent_test_tools
from src.config import load_config
from src.distribute.claude_config import install_approved_tools
from src.distribute.digest_generator import generate_digest, save_digest
from src.distribute.github_publisher import publish_to_github
from src.distribute.obsidian import save_to_obsidian
from src.distribute.telegram_voice import generate_voice_memo, send_telegram_memo, save_transcript
from src.models import NewsItem, RankedItem, TestResult
from src.pipeline.aggregator import aggregate
from src.pipeline.ranker import rank_basic, rank_with_llm, save_ranked
from src.scrapers.github_trending import GitHubTrendingScraper
from src.scrapers.hackernews import HackerNewsScraper
from src.scrapers.producthunt import ProductHuntScraper
from src.scrapers.reddit import RedditScraper
from src.scrapers.rss_feeds import RSSFeedScraper
from src.scrapers.twitter import TwitterScraper
from src.scrapers.youtube import YouTubeScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("pipeline")

# Registry of available scrapers
SCRAPERS = {
    "hackernews": HackerNewsScraper,
    "reddit": RedditScraper,
    "github": GitHubTrendingScraper,
    "rss": RSSFeedScraper,
    "producthunt": ProductHuntScraper,
    "twitter": TwitterScraper,
    "youtube": YouTubeScraper,
}


def scrape(config: dict, sources: list[str] | None = None, run_date: date | None = None) -> list[NewsItem]:
    """Stage 1: Scrape all configured sources."""
    active_sources = sources or list(SCRAPERS.keys())
    all_items: list[NewsItem] = []

    for source_name in active_sources:
        scraper_cls = SCRAPERS.get(source_name)
        if not scraper_cls:
            logger.warning(f"Unknown source: {source_name}, skipping")
            continue

        scraper = scraper_cls(config)
        items = scraper.scrape_with_cache(today=run_date)
        all_items.extend(items)
        logger.info(f"[{source_name}] Got {len(items)} items")

    logger.info(f"Total raw items: {len(all_items)}")
    return all_items


def rank(items: list[NewsItem], config: dict, use_llm: bool = False) -> list[RankedItem]:
    """Stage 2: Aggregate and rank items."""
    aggregated = aggregate(items)
    logger.info(f"After aggregation: {len(aggregated)} unique items")

    if use_llm:
        ranked = rank_with_llm(aggregated, config)
    else:
        ranked = rank_basic(aggregated, config)

    # Only apply threshold when using LLM ranking (basic heuristics score lower)
    if use_llm:
        threshold = config.get("ranking", {}).get("min_score_threshold", 0)
        if threshold:
            ranked = [r for r in ranked if r.total_score >= threshold]
            logger.info(f"After threshold ({threshold}): {len(ranked)} items")

    return ranked


def test(ranked: list[RankedItem], config: dict) -> list[TestResult]:
    """Stage 3: Test top-ranked tools using Claude Code agents."""
    results = agent_test_tools(ranked, config)
    evaluate(results)
    return results


def distribute(
    ranked: list[RankedItem],
    test_results: list[TestResult] | None,
    config: dict,
    run_date: date | None = None,
) -> None:
    """Stage 4: Generate digest, install tools, publish to GitHub."""
    run_date = run_date or date.today()

    # 1. Generate and save digest
    digest = generate_digest(ranked, test_results, run_date)
    digest_path = save_digest(digest, run_date)
    print(f"\nDigest saved to: {digest_path}")
    print("\n" + digest)

    # 2. Install approved tools into Claude Code config
    if test_results:
        installed = install_approved_tools(test_results)
        if installed["mcp_servers"] or installed["skills"]:
            logger.info(
                f"Installed into Claude Code: "
                f"{installed['mcp_servers']} MCP servers, {installed['skills']} skills"
            )

    # 3. Save to Obsidian vault (if configured)
    obsidian_vault = config.get("distribution", {}).get("obsidian_vault", "")
    if obsidian_vault:
        save_to_obsidian(digest, obsidian_vault, run_date)

    # 4. Publish to GitHub (if configured)
    github_repo = config.get("distribution", {}).get("github_repo", "")
    if github_repo:
        publish_to_github(digest, ranked, test_results, repo=github_repo, run_date=run_date)

    # 5. Send Telegram voice memo (if configured)
    telegram_enabled = config.get("distribution", {}).get("telegram_enabled", False)
    if telegram_enabled:
        try:
            telegram_chat_ids = config.get("distribution", {}).get("telegram_chat_ids", [])
            voice_tone = config.get("distribution", {}).get("telegram_voice_tone", "conversational")
            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

            if not bot_token:
                logger.warning("TELEGRAM_BOT_TOKEN not set. Skipping voice memo.")
            elif not telegram_chat_ids:
                logger.warning("No Telegram chat IDs configured. Skipping voice memo.")
            else:
                # Generate voice memo
                audio_bytes, transcript = generate_voice_memo(ranked, test_results, voice_tone)
                # Save transcript
                save_transcript(transcript, run_date)
                # Send via Telegram
                if send_telegram_memo(audio_bytes, transcript, bot_token, telegram_chat_ids, run_date):
                    logger.info("Telegram voice memo sent successfully")
        except Exception as e:
            logger.exception(f"Failed to send Telegram voice memo: {e}")


def print_results(ranked: list[RankedItem]) -> None:
    """Pretty-print ranked results to console."""
    print("\n" + "=" * 70)
    print(f"  AI NEWS DIGEST — {date.today()}")
    print("=" * 70)

    for i, item in enumerate(ranked[:20], 1):
        sources = item.item.raw_data.get("all_sources", [item.item.source.value])
        print(f"\n{i:2d}. [{item.total_score}/40] {item.item.title}")
        print(f"    {item.item.url}")
        print(f"    Sources: {', '.join(sources)} | Score: {item.item.score} | Tags: {', '.join(item.item.tags[:5])}")
        if item.reasoning:
            print(f"    Reason: {item.reasoning}")

    print("\n" + "=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="AI News Automation Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Scrape + rank only, skip testing and distribution")
    parser.add_argument("--digest", action="store_true", help="Scrape + rank + generate digest (skip agent testing)")
    parser.add_argument("--sources", nargs="+", help="Specific sources to scrape (default: all)")
    parser.add_argument("--stage", choices=["scrape", "rank", "test", "distribute"], help="Run a single stage")
    parser.add_argument("--date", type=str, help="Run date (YYYY-MM-DD), default: today")
    parser.add_argument("--llm", action="store_true", help="Use LLM for ranking (auto-detects Ollama/Anthropic/OpenAI)")
    parser.add_argument("--provider", choices=["ollama", "lmstudio", "anthropic", "openai"], help="LLM provider (default: auto-detect)")
    parser.add_argument("--model", type=str, help="LLM model override (e.g. llama3.1, claude-sonnet-4-6, gpt-4o-mini)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON instead of pretty-print")
    parser.add_argument("--agent", choices=["claude", "opencode"], help="Coding agent for tool testing (default: auto-detect)")
    parser.add_argument("--max-test", type=int, help="Max number of tools to test (default: from config)")
    parser.add_argument("--no-setup", action="store_true", help="Skip first-run setup wizard")

    args = parser.parse_args()

    # First-run setup wizard
    if not Path("config.yaml").exists() and not args.no_setup:
        from src.setup_wizard import run_wizard
        run_wizard()
        return  # Don't auto-run pipeline after first-time setup

    run_date = date.fromisoformat(args.date) if args.date else date.today()

    # Set up file logging
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / f"pipeline-{run_date}.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(file_handler)

    logger.info(f"Pipeline started for {run_date}")

    config = load_config()

    # Apply CLI overrides for LLM provider/model
    if args.provider:
        config.setdefault("ranking", {})["provider"] = args.provider
    if args.model:
        config.setdefault("ranking", {})["model"] = args.model

    # Stage 1: Scrape
    items = scrape(config, sources=args.sources, run_date=run_date)
    if not items:
        logger.warning("No items scraped. Exiting.")
        return

    if args.stage == "scrape":
        print(json.dumps([item.to_dict() for item in items], indent=2))
        return

    # Stage 2: Rank
    ranked = rank(items, config, use_llm=args.llm)
    save_ranked(ranked, today=run_date)

    if args.stage == "rank" or args.dry_run:
        if args.json:
            print(json.dumps([r.to_dict() for r in ranked], indent=2))
        else:
            print_results(ranked)
        return

    # --digest mode: skip testing, go straight to distribution
    if args.digest:
        distribute(ranked, test_results=None, config=config, run_date=run_date)
        logger.info("Pipeline complete (digest mode).")
        return

    # Stage 3: Test
    if args.agent:
        config.setdefault("testing", {})["agent"] = args.agent
    if args.max_test:
        config.setdefault("ranking", {})["max_tools_to_test"] = args.max_test

    results = test(ranked, config)

    # Print test report
    report = generate_report(results)
    print(report)

    if args.stage == "test":
        return

    # Stage 4: Distribute
    distribute(ranked, test_results=results, config=config, run_date=run_date)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
