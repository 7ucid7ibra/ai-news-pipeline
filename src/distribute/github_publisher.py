"""GitHub Publisher: pushes daily digests and tool data to a public GitHub repo.

Uses the gh CLI for all operations (already authenticated).
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import date
from pathlib import Path

from src.models import RankedItem, TestResult

logger = logging.getLogger(__name__)


def publish_to_github(
    digest_content: str,
    ranked: list[RankedItem],
    test_results: list[TestResult] | None = None,
    repo: str = "",
    run_date: date | None = None,
    dry_run: bool = False,
) -> bool:
    """Publish daily digest and data to a GitHub repository.

    Args:
        digest_content: Markdown digest string
        ranked: Ranked items for JSON export
        test_results: Optional test results
        repo: GitHub repo in "owner/name" format
        run_date: Date for filenames
        dry_run: If True, show what would happen without pushing

    Returns:
        True if published successfully
    """
    run_date = run_date or date.today()

    if not repo:
        logger.info("No GitHub repo configured, skipping publish")
        return False

    if not _gh_available():
        logger.warning("gh CLI not available, skipping GitHub publish")
        return False

    if dry_run:
        logger.info(f"[DRY RUN] Would publish digest for {run_date} to {repo}")
        return True

    try:
        # Ensure repo exists and is cloned
        repo_dir = _ensure_repo(repo)
        if not repo_dir:
            return False

        # Write digest
        digest_dir = repo_dir / "digests"
        digest_dir.mkdir(exist_ok=True)
        digest_file = digest_dir / f"{run_date}.md"
        digest_file.write_text(digest_content)

        # Write JSON data
        data_dir = repo_dir / "data"
        data_dir.mkdir(exist_ok=True)
        data_file = data_dir / f"{run_date}.json"
        data_file.write_text(json.dumps(
            {
                "date": str(run_date),
                "items_count": len(ranked),
                "items": [r.to_dict() for r in ranked[:50]],  # Top 50
                "tested": len(test_results) if test_results else 0,
            },
            indent=2,
        ))

        # Update README with latest digest link
        _update_readme(repo_dir, run_date)

        # Git add, commit, push
        _git_push(repo_dir, run_date)

        logger.info(f"Published digest for {run_date} to {repo}")
        return True

    except Exception:
        logger.exception(f"Failed to publish to GitHub repo: {repo}")
        return False


def _gh_available() -> bool:
    """Check if gh CLI is available."""
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _ensure_repo(repo: str) -> Path | None:
    """Ensure the GitHub repo is cloned locally."""
    repo_dir = Path.home() / ".ainews" / "publish" / repo.replace("/", "_")

    if repo_dir.exists():
        # Pull latest
        subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=repo_dir,
            capture_output=True,
            timeout=30,
        )
        return repo_dir

    # Clone the repo
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["gh", "repo", "clone", repo, str(repo_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        # Repo might not exist yet — create it
        logger.info(f"Repo {repo} not found, creating...")
        create_result = subprocess.run(
            ["gh", "repo", "create", repo, "--public", "--description",
             "Daily AI tools and news digest — auto-generated"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if create_result.returncode != 0:
            logger.error(f"Failed to create repo: {create_result.stderr}")
            return None

        # Clone the newly created repo
        subprocess.run(
            ["gh", "repo", "clone", repo, str(repo_dir)],
            capture_output=True,
            timeout=60,
        )

    return repo_dir if repo_dir.exists() else None


def _update_readme(repo_dir: Path, run_date: date) -> None:
    """Update the repo README with a link to the latest digest."""
    readme = repo_dir / "README.md"

    content = f"""# AI Tools Daily

Automated daily digest of the best new AI tools, models, and resources.

## Latest Digest

- [{run_date}](digests/{run_date}.md)

## How It Works

This repository is automatically updated daily by an AI-powered pipeline that:
1. Scrapes AI news from HackerNews, Reddit, GitHub, RSS feeds, and Product Hunt
2. Uses Claude to rank items by novelty, practicality, impact, and testability
3. Deploys Claude Code agents to install and test the top tools
4. Publishes the results here

## Structure

```
digests/     # Daily markdown digests
data/        # Raw JSON data for each day
```

---
*Auto-generated by [AI News Automation](https://github.com/ai-news-automation)*
"""
    readme.write_text(content)


def _git_push(repo_dir: Path, run_date: date) -> None:
    """Stage, commit, and push changes."""
    subprocess.run(["git", "add", "-A"], cwd=repo_dir, capture_output=True)

    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_dir,
        capture_output=True,
    )

    if result.returncode == 0:
        logger.info("No changes to commit")
        return

    subprocess.run(
        ["git", "commit", "-m", f"Daily digest: {run_date}"],
        cwd=repo_dir,
        capture_output=True,
        timeout=15,
    )
    subprocess.run(
        ["git", "push"],
        cwd=repo_dir,
        capture_output=True,
        timeout=30,
    )
