"""Claude Code Config Installer: auto-installs approved tools into Claude Code.

Handles two types of installations:
1. MCP Servers → added to ~/.claude/settings.json under mcpServers
2. Claude Skills → written to ~/.claude/skills/{tool_name}/
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from src.models import TestResult, TestVerdict

logger = logging.getLogger(__name__)

CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
SKILLS_DIR = CLAUDE_DIR / "skills"
BACKUP_DIR = CLAUDE_DIR / "backups"


def install_approved_tools(
    results: list[TestResult],
    dry_run: bool = False,
) -> dict:
    """Install all approved tools into Claude Code configuration.

    Args:
        results: Test results (only PASS verdicts will be installed)
        dry_run: If True, show what would be installed without changing anything

    Returns:
        Dict with counts of installed items
    """
    passed = [r for r in results if r.verdict == TestVerdict.PASS]
    if not passed:
        logger.info("No tools to install (none passed testing)")
        return {"mcp_servers": 0, "skills": 0}

    installed = {"mcp_servers": 0, "skills": 0}

    for result in passed:
        mcp_config = result.recommended_config.get("mcp_config")
        skill_config = result.recommended_config.get("skill_config")

        if mcp_config:
            if dry_run:
                logger.info(f"[DRY RUN] Would install MCP server: {result.item.item.title[:50]}")
            else:
                if _install_mcp_server(result, mcp_config):
                    installed["mcp_servers"] += 1

        if skill_config:
            if dry_run:
                logger.info(f"[DRY RUN] Would install skill: {result.item.item.title[:50]}")
            else:
                if _install_skill(result, skill_config):
                    installed["skills"] += 1

    logger.info(
        f"Installed {installed['mcp_servers']} MCP servers, "
        f"{installed['skills']} skills"
    )
    return installed


def _install_mcp_server(result: TestResult, mcp_config: dict) -> bool:
    """Add an MCP server to Claude Code settings.json."""
    try:
        # Backup current settings
        _backup_settings()

        # Load current settings
        settings = _load_settings()

        # Add MCP server config
        mcp_servers = settings.setdefault("mcpServers", {})

        # Generate a safe key name from the tool title
        key = _safe_key(result.item.item.title)

        if key in mcp_servers:
            logger.info(f"MCP server '{key}' already configured, skipping")
            return False

        mcp_servers[key] = mcp_config
        _save_settings(settings)

        logger.info(f"Installed MCP server: {key}")
        return True

    except Exception:
        logger.exception(f"Failed to install MCP server: {result.item.item.title[:50]}")
        return False


def _install_skill(result: TestResult, skill_config: dict) -> bool:
    """Install a Claude Code skill."""
    try:
        key = _safe_key(result.item.item.title)
        skill_dir = SKILLS_DIR / key
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write skill file
        skill_content = skill_config.get("content", "")
        if not skill_content:
            # Generate a basic skill from the test result
            skill_content = _generate_skill_content(result)

        skill_file = skill_dir / f"{key}.md"
        skill_file.write_text(skill_content)

        logger.info(f"Installed skill: {key} at {skill_file}")
        return True

    except Exception:
        logger.exception(f"Failed to install skill: {result.item.item.title[:50]}")
        return False


def _generate_skill_content(result: TestResult) -> str:
    """Generate a basic skill markdown file from test results."""
    item = result.item.item
    return f"""# {item.title}

{item.description}

## Installation

```bash
{result.install_command}
```

## Usage

{result.evaluation}

## Source

- URL: {item.url}
- Discovered: {item.timestamp.strftime('%Y-%m-%d') if item.timestamp else 'unknown'}
- Score: {result.item.total_score}/40
"""


def _load_settings() -> dict:
    """Load Claude Code settings.json."""
    if SETTINGS_PATH.exists():
        return json.loads(SETTINGS_PATH.read_text())
    return {}


def _save_settings(settings: dict) -> None:
    """Write Claude Code settings.json."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")


def _backup_settings() -> Path | None:
    """Create a timestamped backup of settings.json."""
    if not SETTINGS_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"settings_{timestamp}.json"
    shutil.copy2(SETTINGS_PATH, backup_path)
    logger.debug(f"Backed up settings to {backup_path}")
    return backup_path


def _safe_key(title: str) -> str:
    """Convert a title to a safe filesystem/JSON key."""
    import re
    key = title.lower()
    key = key.split(":")[0]  # Take part before colon (e.g., "user/repo: desc" → "user/repo")
    key = re.sub(r"[^a-z0-9]+", "-", key)
    key = key.strip("-")[:50]
    return key
