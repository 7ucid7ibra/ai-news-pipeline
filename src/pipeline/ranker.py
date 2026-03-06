"""Ranker: scores items using LLM (Ollama, Anthropic, OpenAI) or basic heuristics."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from pathlib import Path

import requests

from src.models import NewsItem, RankedItem

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"

RANKING_SYSTEM_PROMPT = """\
You are an expert AI tools and news evaluator. Your job is to score AI news items \
to help a developer decide what's worth paying attention to TODAY.

You evaluate each item on 4 dimensions (0-10 each):

1. **Novelty** (0-10): Is this genuinely NEW?
   - 9-10: Brand new tool/model launch, first-of-its-kind capability
   - 6-8: Significant update to existing tool, new approach to known problem
   - 3-5: Incremental update, another tool in a crowded space
   - 0-2: Old news, rehash, opinion piece about known topic

2. **Practicality** (0-10): Can a developer install and USE this today?
   - 9-10: pip/npm install, ready to use, clear docs, open source
   - 6-8: Available but needs some setup, API key, or configuration
   - 3-5: Announced but limited access, waitlist, or enterprise only
   - 0-2: Research paper, concept, not yet released, or meme/discussion

3. **Impact** (0-10): Does this meaningfully improve AI/dev workflows?
   - 9-10: Game-changing capability, 10x improvement in key workflow
   - 6-8: Solid improvement, saves meaningful time, good UX
   - 3-5: Nice-to-have, marginal improvement, niche use case
   - 0-2: Minimal practical value, entertainment, or not AI-tool related

4. **Testability** (0-10): Can an AI coding agent install and test this in 5 minutes?
   - 9-10: CLI tool, MCP server, pip package — install and verify in seconds
   - 6-8: Needs an API key or brief config but doable quickly
   - 3-5: Requires account setup, hardware, or complex environment
   - 0-2: Not software (news article, image, video), or needs GPU/cloud

Focus especially on:
- New CLI tools, MCP servers, and dev extensions
- Open source AI tools with GitHub repos
- New model releases that developers can actually use
- Creative implementations and workflows

Deprioritize:
- Memes, jokes, opinion pieces
- Enterprise-only announcements
- News about AI policy/regulation (unless it directly affects tool usage)
- Paywalled content without a tool component"""

# Default models per provider
DEFAULT_MODELS = {
    "ollama": "llama3.1",
    "lmstudio": "loaded",
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",
}


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str, system: str, config: dict) -> str:
    """Call Ollama's local API."""
    model = config.get("ranking", {}).get("model", DEFAULT_MODELS["ollama"])
    base_url = config.get("ranking", {}).get("ollama_url", "http://localhost:11434")

    resp = requests.post(
        f"{base_url}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 8192},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _call_anthropic(prompt: str, system: str, config: dict) -> str:
    """Call Anthropic's Claude API."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    model = config.get("ranking", {}).get("model", DEFAULT_MODELS["anthropic"])
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _call_lmstudio(prompt: str, system: str, config: dict) -> str:
    """Call LM Studio's local OpenAI-compatible API."""
    model = config.get("ranking", {}).get("model", DEFAULT_MODELS["lmstudio"])
    base_url = config.get("ranking", {}).get("lmstudio_url", "http://localhost:1234")

    resp = requests.post(
        f"{base_url}/v1/chat/completions",
        headers={"Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 8192,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_openai(prompt: str, system: str, config: dict) -> str:
    """Call OpenAI's API."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = config.get("ranking", {}).get("model", DEFAULT_MODELS["openai"])

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 8192,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


PROVIDERS = {
    "ollama": _call_ollama,
    "lmstudio": _call_lmstudio,
    "anthropic": _call_anthropic,
    "openai": _call_openai,
}


def _detect_provider(config: dict) -> str:
    """Auto-detect which LLM provider to use based on config and available keys."""
    # Explicit config takes priority
    explicit = config.get("ranking", {}).get("provider", "")
    if explicit and explicit in PROVIDERS:
        return explicit

    # Check for local providers first (free)
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            return "ollama"
    except requests.RequestException:
        pass

    lmstudio_url = config.get("ranking", {}).get("lmstudio_url", "http://localhost:1234")
    try:
        resp = requests.get(f"{lmstudio_url}/v1/models", timeout=2)
        if resp.status_code == 200:
            return "lmstudio"
    except requests.RequestException:
        pass

    # Check for API keys
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"

    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rank_basic(items: list[NewsItem], config: dict) -> list[RankedItem]:
    """Basic heuristic ranking (no LLM). Good for testing the pipeline."""
    ranked = []
    for item in items:
        novelty = min(10, int(item.normalized_score / 10))
        practicality = 7 if any(kw in item.title.lower() for kw in ["tool", "launch", "release", "open source"]) else 4
        impact = min(10, item.cross_posted * 3)
        testability = 6 if item.url and "github.com" in item.url else 4

        ranked.append(
            RankedItem(
                item=item,
                novelty=novelty,
                practicality=practicality,
                impact=impact,
                testability=testability,
                reasoning="Scored via basic heuristics (no LLM)",
            )
        )

    ranked.sort(key=lambda x: x.total_score, reverse=True)
    return ranked


def rank_with_llm(items: list[NewsItem], config: dict) -> list[RankedItem]:
    """Rank items using an LLM provider (auto-detected or configured)."""
    provider_name = _detect_provider(config)

    if not provider_name:
        logger.warning(
            "No LLM provider available. Options:\n"
            "  1. Install Ollama (free, local): https://ollama.com\n"
            "  2. Set ANTHROPIC_API_KEY in .env\n"
            "  3. Set OPENAI_API_KEY in .env\n"
            "Falling back to basic ranking."
        )
        return rank_basic(items, config)

    call_fn = PROVIDERS[provider_name]
    model = config.get("ranking", {}).get("model", DEFAULT_MODELS[provider_name])
    logger.info(f"Using LLM provider: {provider_name} (model: {model})")

    # Batch items — 25 per request for quality
    batch_size = 25
    all_ranked: list[RankedItem] = []

    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        logger.info(f"LLM ranking batch {i // batch_size + 1} ({len(batch)} items)...")
        ranked_batch = _rank_batch(call_fn, batch, i, config)
        all_ranked.extend(ranked_batch)

    all_ranked.sort(key=lambda x: x.total_score, reverse=True)
    return all_ranked


def _rank_batch(call_fn, items: list[NewsItem], offset: int, config: dict) -> list[RankedItem]:
    """Send a batch of items to an LLM for ranking."""
    items_text = "\n".join(
        f"{idx}. [{item.source.value}] {item.title}\n"
        f"   URL: {item.url}\n"
        f"   Description: {item.description[:200]}\n"
        f"   Community score: {item.score} | Cross-posted: {item.cross_posted}x | Tags: {', '.join(item.tags[:5])}"
        for idx, item in enumerate(items)
    )

    prompt = f"""Score each of the following {len(items)} AI news items.

{items_text}

Respond with ONLY a JSON array — no markdown, no explanation, no code fences.
Each element must have: index (int), novelty (int 0-10), practicality (int 0-10), impact (int 0-10), testability (int 0-10), reasoning (string, 1 sentence).

Example: [{{"index": 0, "novelty": 7, "practicality": 8, "impact": 6, "testability": 9, "reasoning": "New open-source MCP server, easy to install and test"}}]"""

    try:
        text = call_fn(prompt, RANKING_SYSTEM_PROMPT, config).strip()
        scores = _parse_json_array(text)

        if not scores:
            logger.error(f"Failed to parse LLM response for batch at offset {offset}")
            return [RankedItem(item=item, reasoning="LLM parse failed") for item in items]

    except Exception:
        logger.exception(f"LLM ranking failed for batch at offset {offset}")
        return [RankedItem(item=item, reasoning="LLM ranking failed") for item in items]

    # Map scores back to items
    ranked = []
    scored_indices = set()

    for score_data in scores:
        idx = score_data.get("index", -1)
        if 0 <= idx < len(items) and idx not in scored_indices:
            scored_indices.add(idx)
            ranked.append(
                RankedItem(
                    item=items[idx],
                    novelty=_clamp(score_data.get("novelty", 0)),
                    practicality=_clamp(score_data.get("practicality", 0)),
                    impact=_clamp(score_data.get("impact", 0)),
                    testability=_clamp(score_data.get("testability", 0)),
                    reasoning=score_data.get("reasoning", ""),
                )
            )

    # Add any items that weren't scored
    for idx, item in enumerate(items):
        if idx not in scored_indices:
            ranked.append(RankedItem(item=item, reasoning="Not scored by LLM"))

    return ranked


def _parse_json_array(text: str) -> list[dict] | None:
    """Robustly extract a JSON array from LLM output."""
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    if "```" in text:
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _clamp(value, low: int = 0, high: int = 10) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return 0


def save_ranked(ranked: list[RankedItem], today: date | None = None) -> Path:
    """Save ranked items to JSON."""
    today = today or date.today()
    out_dir = DATA_DIR / "ranked"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{today}.json"
    out_file.write_text(json.dumps([r.to_dict() for r in ranked], indent=2))
    logger.info(f"Saved {len(ranked)} ranked items to {out_file}")
    return out_file
