"""Obsidian Integration: saves daily digests to an Obsidian vault.

Copies the digest markdown to the configured Obsidian vault directory,
with proper frontmatter for Obsidian's metadata system.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


def save_to_obsidian(
    digest_content: str,
    vault_path: str,
    run_date: date | None = None,
    folder: str = "AI News",
) -> Path | None:
    """Save digest to Obsidian vault with YAML frontmatter.

    Args:
        digest_content: Markdown digest string
        vault_path: Path to Obsidian vault root
        run_date: Date for the note
        folder: Subfolder in vault for AI news digests

    Returns:
        Path to created file, or None if failed
    """
    run_date = run_date or date.today()

    if not vault_path:
        logger.debug("[obsidian] No vault path configured, skipping")
        return None

    vault = Path(vault_path)
    if not vault.exists():
        logger.warning(f"[obsidian] Vault not found at {vault_path}")
        return None

    # Create the AI News folder if needed
    target_dir = vault / folder
    target_dir.mkdir(parents=True, exist_ok=True)

    # Add Obsidian frontmatter
    frontmatter = (
        f"---\n"
        f"date: {run_date}\n"
        f"type: ai-digest\n"
        f"tags:\n"
        f"  - ai-news\n"
        f"  - daily-digest\n"
        f"  - auto-generated\n"
        f"---\n\n"
    )

    filename = f"AI Digest {run_date}.md"
    filepath = target_dir / filename
    filepath.write_text(frontmatter + digest_content)

    logger.info(f"[obsidian] Saved digest to {filepath}")
    return filepath
