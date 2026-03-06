"""Agent Tester: spawns coding agent subprocesses to install and evaluate tools.

Supports multiple agent backends:
- claude: Claude Code CLI (`claude --print`)
- opencode: OpenCode CLI (`opencode run`)

Each tool is tested in an isolated temp directory with a 5-minute timeout.
The agent installs the tool, runs basic tests, and reports back.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.models import RankedItem, TestResult, TestVerdict

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"

TEST_PROMPT_TEMPLATE = """\
You are testing a new AI tool to evaluate if it's worth recommending to developers.

## Tool Information
- **Name**: {title}
- **URL**: {url}
- **Description**: {description}
- **Source**: {source}
- **Tags**: {tags}

## Your Task

1. **Investigate**: Visit the URL or repository to understand what this tool does.
2. **Install**: Install the tool using the appropriate method (pip, npm, brew, etc.). \
If it's an MCP server, determine the configuration needed.
3. **Test**: Run a basic functionality test. Try the tool's main feature.
4. **Evaluate**: Assess whether this tool is genuinely useful.

## Rules
- You are in a temporary directory: {workdir}
- You have a maximum of 5 minutes.
- Do NOT modify any system-wide configuration.
- Do NOT install anything globally (use --user, local venv, or npx).
- If the tool requires an API key you don't have, note that but still evaluate the setup process.
- If the tool requires a GPU or special hardware, mark it as SKIP.

## Output Format

After testing, output your evaluation as a JSON block between <evaluation> tags:

<evaluation>
{{
    "verdict": "pass" | "fail" | "skip",
    "install_method": "pip | npm | brew | cargo | mcp | other",
    "install_command": "the exact install command",
    "what_it_does": "1-2 sentence description",
    "test_result": "what happened when you tested it",
    "useful_for": "who would benefit from this tool",
    "security_concerns": ["list", "of", "concerns"] or [],
    "mcp_config": {{}} or null,
    "skill_config": {{}} or null,
    "recommendation": "1-2 sentence recommendation"
}}
</evaluation>
"""


def _detect_agent(config: dict) -> str:
    """Detect which coding agent CLI is available.

    Priority: explicit config → claude → opencode
    """
    explicit = config.get("testing", {}).get("agent", "")
    if explicit in ("claude", "opencode"):
        return explicit

    # Check what's installed
    if shutil.which("claude"):
        return "claude"
    if shutil.which("opencode"):
        return "opencode"

    return ""


def _build_agent_command(agent: str, prompt: str, config: dict) -> list[str]:
    """Build the subprocess command for the chosen agent backend."""
    if agent == "claude":
        return [
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            "--max-turns", "15",
            "-p", prompt,
        ]
    elif agent == "opencode":
        cmd = ["opencode", "run"]
        # Add model override if specified in config
        model = config.get("testing", {}).get("agent_model", "")
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt)
        return cmd
    else:
        raise FileNotFoundError(f"Unknown agent backend: {agent}")


def test_tools(
    ranked_items: list[RankedItem],
    config: dict,
    max_tools: int | None = None,
) -> list[TestResult]:
    """Test top-ranked tools using a coding agent (Claude Code or OpenCode).

    Args:
        ranked_items: Items sorted by score (highest first)
        config: Pipeline config
        max_tools: Override max tools to test (default from config)

    Returns:
        List of TestResult objects
    """
    max_to_test = max_tools or config.get("ranking", {}).get("max_tools_to_test", 10)
    timeout = config.get("testing", {}).get("timeout_seconds", 300)

    agent = _detect_agent(config)
    if not agent:
        logger.error(
            "No coding agent CLI found. Install one of:\n"
            "  - Claude Code: npm install -g @anthropic-ai/claude-code\n"
            "  - OpenCode: see https://opencode.ai/docs/\n"
        )
        return []

    logger.info(f"Using agent backend: {agent}")

    # Only test items that have a GitHub URL or are clearly installable
    testable = [r for r in ranked_items if _is_testable(r)]
    to_test = testable[:max_to_test]

    if not to_test:
        logger.warning("No testable items found in ranked list")
        return []

    logger.info(f"Testing {len(to_test)} tools (timeout: {timeout}s each)...")

    results: list[TestResult] = []

    for i, ranked_item in enumerate(to_test, 1):
        logger.info(
            f"[{i}/{len(to_test)}] Testing: {ranked_item.item.title[:60]}..."
        )
        result = _test_single_tool(ranked_item, timeout, agent, config)
        results.append(result)

        verdict_symbol = {"pass": "+", "fail": "-", "skip": "~"}[result.verdict.value]
        logger.info(
            f"[{i}/{len(to_test)}] [{verdict_symbol}] {result.verdict.value}: "
            f"{ranked_item.item.title[:50]} — {result.evaluation[:80]}"
        )

    # Save results
    _save_results(results)

    passed = sum(1 for r in results if r.verdict == TestVerdict.PASS)
    failed = sum(1 for r in results if r.verdict == TestVerdict.FAIL)
    skipped = sum(1 for r in results if r.verdict == TestVerdict.SKIP)
    logger.info(f"Testing complete: {passed} passed, {failed} failed, {skipped} skipped")

    return results


def _test_single_tool(ranked_item: RankedItem, timeout: int, agent: str, config: dict) -> TestResult:
    """Test a single tool in an isolated temp directory."""
    item = ranked_item.item

    # Create isolated temp directory
    workdir = tempfile.mkdtemp(prefix="ainews_test_")

    try:
        prompt = TEST_PROMPT_TEMPLATE.format(
            title=item.title,
            url=item.url,
            description=item.description[:500],
            source=item.source.value,
            tags=", ".join(item.tags[:10]),
            workdir=workdir,
        )

        cmd = _build_agent_command(agent, prompt, config)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )

        output = result.stdout + result.stderr
        return _parse_agent_output(ranked_item, output)

    except subprocess.TimeoutExpired:
        logger.warning(f"Test timed out for: {item.title[:50]}")
        return TestResult(
            item=ranked_item,
            verdict=TestVerdict.SKIP,
            evaluation=f"Test timed out after {timeout}s",
            test_log="TIMEOUT",
        )

    except FileNotFoundError:
        logger.error(
            f"Agent CLI '{agent}' not found. Install one of:\n"
            "  - Claude Code: npm install -g @anthropic-ai/claude-code\n"
            "  - OpenCode: see https://opencode.ai/docs/"
        )
        return TestResult(
            item=ranked_item,
            verdict=TestVerdict.SKIP,
            evaluation=f"{agent} CLI not available",
            test_log="CLI_NOT_FOUND",
        )

    except Exception as e:
        logger.exception(f"Test failed for: {item.title[:50]}")
        return TestResult(
            item=ranked_item,
            verdict=TestVerdict.FAIL,
            evaluation=f"Test error: {e}",
            test_log=str(e),
        )

    finally:
        # Clean up temp directory
        shutil.rmtree(workdir, ignore_errors=True)


def _parse_agent_output(ranked_item: RankedItem, output: str) -> TestResult:
    """Parse the agent's output to extract the evaluation JSON."""
    import re

    # Look for <evaluation> tags
    match = re.search(r"<evaluation>\s*({.*?})\s*</evaluation>", output, re.DOTALL)

    if match:
        try:
            eval_data = json.loads(match.group(1))
            verdict_str = eval_data.get("verdict", "fail").lower()
            verdict = TestVerdict(verdict_str) if verdict_str in ("pass", "fail", "skip") else TestVerdict.FAIL

            return TestResult(
                item=ranked_item,
                verdict=verdict,
                install_method=eval_data.get("install_method", ""),
                install_command=eval_data.get("install_command", ""),
                test_log=output[-2000:],  # Keep last 2000 chars
                evaluation=eval_data.get("recommendation", eval_data.get("test_result", "")),
                security_concerns=eval_data.get("security_concerns", []),
                recommended_config={
                    k: v for k, v in {
                        "mcp_config": eval_data.get("mcp_config"),
                        "skill_config": eval_data.get("skill_config"),
                    }.items() if v
                },
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse evaluation JSON: {e}")

    # Fallback: no structured output, try to infer from raw output
    output_lower = output.lower()
    if any(w in output_lower for w in ["successfully installed", "works correctly", "test passed"]):
        verdict = TestVerdict.PASS
    elif any(w in output_lower for w in ["error", "failed", "not found", "permission denied"]):
        verdict = TestVerdict.FAIL
    else:
        verdict = TestVerdict.SKIP

    return TestResult(
        item=ranked_item,
        verdict=verdict,
        test_log=output[-2000:],
        evaluation="Parsed from raw output (no structured evaluation found)",
    )


def _is_testable(ranked_item: RankedItem) -> bool:
    """Check if an item is worth testing (has a repo, installable, etc.)."""
    item = ranked_item.item
    url = item.url.lower()

    # GitHub repos are very testable
    if "github.com" in url:
        return True

    # npm packages
    if "npmjs.com" in url:
        return True

    # PyPI packages
    if "pypi.org" in url:
        return True

    # Items with high testability score from LLM
    if ranked_item.testability >= 7:
        return True

    return False


def _save_results(results: list[TestResult]) -> None:
    """Save test results to disk."""
    from datetime import date

    today = date.today()
    out_dir = DATA_DIR / "tested" / str(today)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Summary file
    summary = {
        "date": str(today),
        "total": len(results),
        "passed": sum(1 for r in results if r.verdict == TestVerdict.PASS),
        "failed": sum(1 for r in results if r.verdict == TestVerdict.FAIL),
        "skipped": sum(1 for r in results if r.verdict == TestVerdict.SKIP),
        "results": [r.to_dict() for r in results],
    }

    summary_file = out_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, indent=2))
    logger.info(f"Saved test results to {summary_file}")
