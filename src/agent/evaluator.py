"""Evaluator: processes test results and generates final recommendations."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from src.models import TestResult, TestVerdict

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def evaluate(results: list[TestResult]) -> list[TestResult]:
    """Process test results and return tools worth installing, sorted by quality.

    Returns only passing tools, sorted by their ranking score.
    """
    passed = [r for r in results if r.verdict == TestVerdict.PASS]
    passed.sort(key=lambda r: r.item.total_score, reverse=True)

    if passed:
        logger.info(f"Evaluation complete: {len(passed)} tools recommended")
        for i, r in enumerate(passed, 1):
            logger.info(
                f"  {i}. [{r.item.total_score}/40] {r.item.item.title[:60]}"
                f" — {r.install_method}: {r.install_command}"
            )
    else:
        logger.info("No tools passed testing today")

    return passed


def get_mcp_candidates(results: list[TestResult]) -> list[TestResult]:
    """Filter for tools that can be installed as MCP servers."""
    return [
        r for r in results
        if r.verdict == TestVerdict.PASS
        and r.recommended_config.get("mcp_config")
    ]


def get_skill_candidates(results: list[TestResult]) -> list[TestResult]:
    """Filter for tools that can be installed as Claude Code skills."""
    return [
        r for r in results
        if r.verdict == TestVerdict.PASS
        and r.recommended_config.get("skill_config")
    ]


def get_cli_candidates(results: list[TestResult]) -> list[TestResult]:
    """Filter for tools installable as CLI tools."""
    return [
        r for r in results
        if r.verdict == TestVerdict.PASS
        and r.install_method in ("pip", "npm", "brew", "cargo")
    ]


def generate_report(results: list[TestResult]) -> str:
    """Generate a human-readable evaluation report."""
    passed = [r for r in results if r.verdict == TestVerdict.PASS]
    failed = [r for r in results if r.verdict == TestVerdict.FAIL]
    skipped = [r for r in results if r.verdict == TestVerdict.SKIP]

    lines = [
        f"# AI Tool Evaluation Report — {date.today()}",
        f"",
        f"**Tested:** {len(results)} | **Passed:** {len(passed)} | "
        f"**Failed:** {len(failed)} | **Skipped:** {len(skipped)}",
        "",
    ]

    if passed:
        lines.append("## Recommended Tools")
        lines.append("")
        for r in sorted(passed, key=lambda x: x.item.total_score, reverse=True):
            item = r.item.item
            lines.append(f"### {item.title}")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Install:** `{r.install_command}`")
            lines.append(f"- **Score:** {r.item.total_score}/40")
            lines.append(f"- **Evaluation:** {r.evaluation}")
            if r.security_concerns:
                lines.append(f"- **Security:** {', '.join(r.security_concerns)}")
            lines.append("")

    if failed:
        lines.append("## Failed Tools")
        lines.append("")
        for r in failed:
            lines.append(f"- **{r.item.item.title[:60]}** — {r.evaluation[:100]}")
        lines.append("")

    if skipped:
        lines.append("## Skipped (Not Testable)")
        lines.append("")
        for r in skipped:
            lines.append(f"- **{r.item.item.title[:60]}** — {r.evaluation[:100]}")
        lines.append("")

    return "\n".join(lines)


def load_results(run_date: date | None = None) -> list[TestResult] | None:
    """Load test results from a previous run."""
    run_date = run_date or date.today()
    summary_file = DATA_DIR / "tested" / str(run_date) / "summary.json"

    if not summary_file.exists():
        return None

    try:
        data = json.loads(summary_file.read_text())
        logger.info(
            f"Loaded {data['total']} results from {run_date}: "
            f"{data['passed']} passed, {data['failed']} failed, {data['skipped']} skipped"
        )
        return data  # Return raw dict for now; full deserialization if needed
    except Exception:
        logger.exception(f"Failed to load results from {summary_file}")
        return None
