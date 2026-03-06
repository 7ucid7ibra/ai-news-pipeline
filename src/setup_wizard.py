"""Interactive first-run setup wizard for AI News Automation.

Runs automatically when config.yaml doesn't exist, or manually via:
    python -m src.setup_wizard
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config.example.yaml"
ENV_PATH = PROJECT_ROOT / ".env"

# ---------------------------------------------------------------------------
# ANSI colors (stdlib only)
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RED = "\033[31m"
RESET = "\033[0m"

CHECK = f"{GREEN}[OK]{RESET}"
WARN = f"{YELLOW}[!!]{RESET}"
FAIL = f"{RED}[--]{RESET}"

# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------


def heading(step: int, total: int, title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {BOLD}Step {step}/{total}: {title}{RESET}")
    print(f"{'─' * 60}\n")


def prompt_yn(question: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = input(f"{question} {suffix}: ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please enter y or n.")


def prompt_choice(options: list[str], prompt_text: str, default: int = 0) -> int:
    for i, opt in enumerate(options):
        marker = f" {CYAN}(default){RESET}" if i == default else ""
        print(f"  {i + 1}. {opt}{marker}")
    while True:
        answer = input(f"\n{prompt_text} [{default + 1}]: ").strip()
        if not answer:
            return default
        try:
            idx = int(answer) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print(f"  Please enter a number 1-{len(options)}.")


def prompt_input(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{label}{suffix}: ").strip()
    return answer or default


def prompt_time(label: str, default: str = "06:00") -> str:
    while True:
        answer = prompt_input(label, default)
        if re.match(r"^\d{2}:\d{2}$", answer):
            h, m = answer.split(":")
            if 0 <= int(h) <= 23 and 0 <= int(m) <= 59:
                return answer
        print("  Please enter a valid time in HH:MM format.")


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def check_python_deps() -> dict[str, bool]:
    """Check which required Python packages are importable."""
    packages = {
        "pyyaml": "yaml",
        "requests": "requests",
        "feedparser": "feedparser",
        "praw": "praw",
        "rapidfuzz": "rapidfuzz",
    }
    results = {}
    for pkg_name, import_name in packages.items():
        try:
            __import__(import_name)
            results[pkg_name] = True
        except ImportError:
            results[pkg_name] = False
    return results


def check_optional_tools() -> dict[str, dict]:
    """Check which optional CLI tools are installed."""
    tools = {
        "yt-dlp": "YouTube scraping",
        "ollama": "Local LLM for ranking (free)",
        "claude": "Claude Code agent for tool testing",
        "opencode": "OpenCode agent for tool testing",
    }
    results = {}
    for tool, desc in tools.items():
        results[tool] = {
            "installed": shutil.which(tool) is not None,
            "description": desc,
        }
    return results


def detect_llm_providers() -> list[dict]:
    """Detect available LLM providers."""
    providers = []

    # Ollama
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            providers.append({
                "name": "ollama",
                "label": "Ollama (local, free)",
                "available": True,
                "models": models,
            })
    except Exception:
        pass

    # LM Studio
    try:
        import requests
        resp = requests.get("http://localhost:1234/v1/models", timeout=2)
        if resp.status_code == 200:
            models = [m["id"] for m in resp.json().get("data", [])]
            providers.append({
                "name": "lmstudio",
                "label": "LM Studio (local, free)",
                "available": True,
                "models": models,
            })
    except Exception:
        pass

    # Anthropic
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key and ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    providers.append({
        "name": "anthropic",
        "label": "Anthropic (Claude API)" + (" — key found" if key else ""),
        "available": bool(key),
        "models": ["claude-sonnet-4-6"],
    })

    # OpenAI
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key and ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    providers.append({
        "name": "openai",
        "label": "OpenAI (GPT API)" + (" — key found" if key else ""),
        "available": bool(key),
        "models": ["gpt-4o-mini"],
    })

    return providers


# ---------------------------------------------------------------------------
# Wizard steps
# ---------------------------------------------------------------------------

TOTAL_STEPS = 9


def step_check_deps() -> dict:
    """Step 1: Check Python dependencies."""
    heading(1, TOTAL_STEPS, "Python Dependencies")

    deps = check_python_deps()
    all_ok = True
    for pkg, installed in deps.items():
        status = CHECK if installed else FAIL
        print(f"  {status} {pkg}")
        if not installed:
            all_ok = False

    if all_ok:
        print(f"\n  All dependencies installed.")
    else:
        print()
        if prompt_yn("  Install missing dependencies now? (pip install -e .)", default=True):
            print(f"\n  Installing...\n")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", str(PROJECT_ROOT)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"  {CHECK} Dependencies installed successfully.")
            else:
                print(f"  {FAIL} Installation failed. Try manually: pip install -e .")
                print(f"  {DIM}{result.stderr[:300]}{RESET}")

    return {"deps_ok": all_ok}


def step_check_tools() -> dict:
    """Step 2: Check optional tools."""
    heading(2, TOTAL_STEPS, "Optional Tools")

    tools = check_optional_tools()
    for name, info in tools.items():
        status = CHECK if info["installed"] else WARN
        print(f"  {status} {name:15s} {info['description']}")

    if not tools["yt-dlp"]["installed"]:
        print(f"\n  {DIM}Install yt-dlp for YouTube: pip install yt-dlp{RESET}")
    if not tools["ollama"]["installed"] and not tools.get("lmstudio", {}).get("installed"):
        print(f"  {DIM}Install Ollama for free local LLM: https://ollama.com{RESET}")

    return {"tools": tools}


def step_llm_provider() -> dict:
    """Step 3: LLM provider selection."""
    heading(3, TOTAL_STEPS, "LLM Provider")

    providers = detect_llm_providers()
    available = [p for p in providers if p["available"]]

    api_keys: dict[str, str] = {}

    if not available:
        print("  No LLM providers detected.\n")
        print("  Options:")
        print("    1. Install Ollama (free, local): https://ollama.com")
        print("    2. Install LM Studio (free, local): https://lmstudio.ai")
        print("    3. Enter an Anthropic API key")
        print("    4. Enter an OpenAI API key")
        print("    5. Skip (use basic heuristic ranking)\n")

        choice = prompt_choice(
            ["Install Ollama later", "Install LM Studio later",
             "Enter Anthropic API key", "Enter OpenAI API key", "Skip for now"],
            "Choose", default=4
        )

        if choice == 2:
            key = prompt_input("  Anthropic API key (sk-ant-...)")
            if key:
                api_keys["ANTHROPIC_API_KEY"] = key
                return {"provider": "anthropic", "model": "claude-sonnet-4-6", "api_keys": api_keys}
        elif choice == 3:
            key = prompt_input("  OpenAI API key (sk-...)")
            if key:
                api_keys["OPENAI_API_KEY"] = key
                return {"provider": "openai", "model": "gpt-4o-mini", "api_keys": api_keys}

        print(f"\n  {DIM}Will use basic heuristic ranking (no LLM).{RESET}")
        return {"provider": "", "model": "", "api_keys": api_keys}

    # Show available providers
    print("  Detected providers:")
    choice = prompt_choice(
        [p["label"] for p in available],
        "Which provider for ranking?",
        default=0,
    )
    selected = available[choice]

    # Model selection
    model = ""
    if selected["models"]:
        if len(selected["models"]) == 1:
            model = selected["models"][0]
            print(f"\n  Model: {model}")
        else:
            print(f"\n  Available models:")
            # Add descriptions to model names for clarity
            model_labels = []
            for m in selected["models"]:
                if "gemma3:12b" in m:
                    label = f"{m} (recommended, best quality)"
                elif "gemma3:" in m or "mistral" in m or "neural-chat" in m:
                    label = f"{m} (good balance)"
                elif ":0.5b" in m or ":1b" in m or ":2b" in m or "nano" in m:
                    label = f"{m} (fast, lower quality)"
                elif "llava" in m:
                    label = f"{m} (vision model, not ideal for ranking)"
                else:
                    label = m
                model_labels.append(label)
            model_idx = prompt_choice(model_labels, "Which model?", default=0)
            model = selected["models"][model_idx]

    # If API provider selected but no key, prompt for it
    if selected["name"] == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        existing = _read_env_key("ANTHROPIC_API_KEY")
        if not existing:
            key = prompt_input("\n  Anthropic API key (sk-ant-...)")
            if key:
                api_keys["ANTHROPIC_API_KEY"] = key
    elif selected["name"] == "openai" and not os.environ.get("OPENAI_API_KEY"):
        existing = _read_env_key("OPENAI_API_KEY")
        if not existing:
            key = prompt_input("\n  OpenAI API key (sk-...)")
            if key:
                api_keys["OPENAI_API_KEY"] = key

    return {"provider": selected["name"], "model": model, "api_keys": api_keys}


def step_sources() -> dict:
    """Step 4: News source selection."""
    heading(4, TOTAL_STEPS, "News Sources")

    tools = check_optional_tools()
    sources = [
        {"key": "hackernews", "label": "Hacker News", "needs": None},
        {"key": "reddit", "label": "Reddit", "needs": None},
        {"key": "github", "label": "GitHub Trending", "needs": None},
        {"key": "rss", "label": "RSS Feeds (8 feeds)", "needs": None},
        {"key": "producthunt", "label": "Product Hunt", "needs": None},
        {"key": "twitter", "label": "Twitter/X", "needs": "playwright"},
        {"key": "youtube", "label": "YouTube", "needs": "yt-dlp"},
    ]

    # Default: enable all except those missing required tools
    enabled = []
    for s in sources:
        if s["needs"] and not tools.get(s["needs"], {}).get("installed", False):
            enabled.append(False)
        else:
            enabled.append(True)

    def show_sources():
        for i, s in enumerate(sources):
            check = "x" if enabled[i] else " "
            note = ""
            if s["needs"] and not tools.get(s["needs"], {}).get("installed", False):
                note = f" {DIM}(needs {s['needs']}){RESET}"
            print(f"  {i + 1}. [{check}] {s['label']}{note}")

    show_sources()
    print(f"\n  {DIM}Type numbers to toggle, Enter to confirm.{RESET}")

    while True:
        answer = input("\n  Toggle: ").strip()
        if not answer:
            break
        for part in answer.replace(",", " ").split():
            try:
                idx = int(part) - 1
                if 0 <= idx < len(sources):
                    enabled[idx] = not enabled[idx]
            except ValueError:
                pass
        print()
        show_sources()

    enabled_sources = [s["key"] for s, e in zip(sources, enabled) if e]

    # Install optional dependencies
    if "youtube" in enabled_sources and not shutil.which("yt-dlp"):
        print(f"\n  {WARN} YouTube requires yt-dlp.")
        if prompt_yn("  Install yt-dlp now?", default=True):
            print(f"\n  Installing yt-dlp...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "yt-dlp"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"  {CHECK} yt-dlp installed successfully.")
            else:
                print(f"  {FAIL} Installation failed. Install manually: pip install yt-dlp")

    if "twitter" in enabled_sources and not shutil.which("playwright"):
        print(f"\n  {WARN} Twitter requires playwright.")
        if prompt_yn("  Install playwright now?", default=True):
            print(f"\n  Installing playwright...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"  {CHECK} Playwright installed successfully.")
            else:
                print(f"  {FAIL} Installation failed. Install manually: pip install playwright")

    # Reddit credentials (optional)
    reddit_creds: dict[str, str] = {}
    if "reddit" in enabled_sources:
        print(f"\n  {DIM}Reddit works without API credentials (public JSON fallback).{RESET}")
        if prompt_yn("  Set up Reddit API for better rate limits?", default=False):
            reddit_creds["REDDIT_CLIENT_ID"] = prompt_input("    Client ID")
            reddit_creds["REDDIT_CLIENT_SECRET"] = prompt_input("    Client Secret")

    return {"enabled_sources": enabled_sources, "reddit_creds": reddit_creds}


def step_agent() -> dict:
    """Step 5: Coding agent for tool testing."""
    heading(5, TOTAL_STEPS, "Tool Testing (Optional)")

    claude_installed = shutil.which("claude") is not None
    opencode_installed = shutil.which("opencode") is not None

    if claude_installed:
        print(f"  {CHECK} Claude Code detected — tool testing ready.")
        return {"agent": "claude", "tool_testing": True}

    if opencode_installed:
        print(f"  {CHECK} OpenCode detected — tool testing ready.")
        return {"agent": "opencode", "tool_testing": True}

    print(f"  {DIM}Tool testing installs and evaluates AI tools automatically.")
    print(f"  Results are included in your daily digest and Obsidian vault.{RESET}")
    print()
    print(f"  {WARN} No coding agent installed.")
    print()

    choice = prompt_choice(
        [
            "Install OpenCode (recommended, open source, works with any LLM)",
            "Install Claude Code (requires Anthropic account)",
            "Skip tool testing for now",
        ],
        "Choose",
        default=0,
    )

    if choice == 0:
        print(f"\n  Installing OpenCode...")
        result = subprocess.run(
            ["brew", "install", "opencode"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and shutil.which("opencode"):
            print(f"  {CHECK} OpenCode installed successfully.")
            return {"agent": "opencode", "tool_testing": True}
        else:
            print(f"  {FAIL} Installation failed. Install manually:")
            print(f"  {DIM}  brew install opencode{RESET}")
            print(f"  {DIM}  Then re-run: python -m src.setup_wizard{RESET}")
            return {"agent": "", "tool_testing": False}

    elif choice == 1:
        print(f"\n  Installing Claude Code...")
        result = subprocess.run(
            ["npm", "install", "-g", "@anthropic-ai/claude-code"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and shutil.which("claude"):
            print(f"  {CHECK} Claude Code installed successfully.")
            return {"agent": "claude", "tool_testing": True}
        else:
            print(f"  {FAIL} Installation failed. Install manually:")
            print(f"  {DIM}  npm install -g @anthropic-ai/claude-code{RESET}")
            return {"agent": "", "tool_testing": False}

    else:
        print(f"  {DIM}Skipping tool testing. Add it later by re-running the wizard.{RESET}")
        return {"agent": "", "tool_testing": False}


def step_distribution() -> dict:
    """Step 6: Distribution options."""
    heading(6, TOTAL_STEPS, "Distribution")

    obsidian_vault = ""
    if prompt_yn("Save digests to an Obsidian vault?", default=False):
        obsidian_vault = prompt_input("  Vault path", default="~/Documents/Obsidian")
        obsidian_vault = str(Path(obsidian_vault).expanduser())
        if not Path(obsidian_vault).exists():
            print(f"  {WARN} Path doesn't exist. Open Obsidian and create your vault at that path first.")

    github_repo = ""
    if prompt_yn("Publish digests to a GitHub repo?", default=False):
        github_repo = prompt_input("  Repo (owner/name)", default="")

    return {"obsidian_vault": obsidian_vault, "github_repo": github_repo}


def step_telegram_voice() -> dict:
    """Step 7: Telegram voice memo (optional)."""
    heading(7, TOTAL_STEPS, "Telegram Voice Memo (Optional)")

    telegram_enabled = prompt_yn("Receive daily digest as a voice memo via Telegram?", default=False)

    telegram_chat_ids = []
    voice_tone = ""

    if telegram_enabled:
        print(f"\n  {DIM}You'll need:1. Telegram Bot Token (create via @BotFather on Telegram)
2. Your Telegram Chat ID (send /start to your bot to get it)
3. ElevenLabs API Key (free tier available at elevenlabs.io){RESET}")

        chat_id_input = prompt_input("\n  Your Telegram Chat ID")
        if chat_id_input:
            telegram_chat_ids = [chat_id_input]
            print(f"  {DIM}(You can add more chat IDs later in config.yaml){RESET}")

        voice_tone = prompt_input(
            "\n  Voice tone/style (e.g., 'casual tech bro', 'professional analyst')",
            default="conversational tech enthusiast",
        )

    return {
        "telegram_enabled": telegram_enabled,
        "telegram_chat_ids": telegram_chat_ids,
        "voice_tone": voice_tone,
    }


def step_schedule() -> dict:
    """Step 8: Schedule setup."""
    heading(8, TOTAL_STEPS, "Schedule")

    schedule_time = prompt_time("Run the pipeline daily at what time?", default="06:00")

    scheduler_installed = False
    if sys.platform == "darwin":
        if prompt_yn("Install macOS launchd scheduler?", default=True):
            install_script = PROJECT_ROOT / "scheduler" / "install.sh"
            if install_script.exists():
                # Update plist with custom time
                _update_plist_time(schedule_time)
                result = subprocess.run(
                    ["bash", str(install_script), "install"],
                    capture_output=True,
                    text=True,
                    cwd=str(PROJECT_ROOT),
                )
                if result.returncode == 0:
                    print(f"\n  {CHECK} Scheduler installed. Pipeline will run daily at {schedule_time}.")
                    scheduler_installed = True
                else:
                    print(f"\n  {FAIL} Scheduler install failed.")
                    print(f"  {DIM}{result.stderr[:200]}{RESET}")
            else:
                print(f"  {WARN} scheduler/install.sh not found.")
    else:
        print(f"  {DIM}Automated scheduling is configured for macOS (launchd).{RESET}")
        print(f"  {DIM}On Linux, set up a cron job: crontab -e{RESET}")

    return {"schedule_time": schedule_time, "scheduler_installed": scheduler_installed}


def step_generate_config(data: dict) -> None:
    """Step 9: Generate config.yaml and .env."""
    heading(9, TOTAL_STEPS, "Saving Configuration")

    import yaml

    # Load example config as template
    with open(EXAMPLE_CONFIG_PATH) as f:
        config = yaml.safe_load(f.read())

    # Apply wizard choices
    config["schedule"]["time"] = data.get("schedule_time", "06:00")

    # Provider / model
    provider = data.get("provider", "")
    if provider:
        config.setdefault("ranking", {})["provider"] = provider
    model = data.get("model", "")
    if model:
        config.setdefault("ranking", {})["model"] = model

    # Sources — remove disabled ones
    enabled = data.get("enabled_sources", [])
    all_source_keys = ["hackernews", "reddit", "github", "rss", "producthunt", "twitter", "youtube"]
    for key in all_source_keys:
        if key not in enabled and key in config.get("sources", {}):
            del config["sources"][key]

    # Distribution
    config.setdefault("distribution", {})["obsidian_vault"] = data.get("obsidian_vault", "")
    config.setdefault("distribution", {})["github_repo"] = data.get("github_repo", "")

    # Telegram voice memo
    config.setdefault("distribution", {})["telegram_enabled"] = data.get("telegram_enabled", False)
    config.setdefault("distribution", {})["telegram_chat_ids"] = data.get("telegram_chat_ids", [])
    config.setdefault("distribution", {})["telegram_voice_tone"] = data.get("voice_tone", "")

    # Agent
    agent = data.get("agent", "")
    if agent:
        config.setdefault("testing", {})["agent"] = agent

    # Write config.yaml
    header = "# Generated by setup wizard — edit freely or re-run: python -m src.setup_wizard\n\n"
    CONFIG_PATH.write_text(header + yaml.dump(config, default_flow_style=False, sort_keys=False))
    source_count = len(enabled) if enabled else len(all_source_keys)
    print(f"  {CHECK} Wrote config.yaml ({source_count} sources, provider: {provider or 'auto'})")

    # Update scheduler run.sh if tool testing is enabled
    if data.get("tool_testing"):
        _update_run_sh(tool_testing=True)
        print(f"  {CHECK} Updated scheduler to include tool testing")

    # Collect all API keys
    api_keys: dict[str, str] = {}
    api_keys.update(data.get("api_keys", {}))
    api_keys.update(data.get("reddit_creds", {}))

    # Write .env
    if api_keys:
        _write_env(api_keys)
        print(f"  {CHECK} Wrote .env ({len(api_keys)} keys)")
    else:
        print(f"  {DIM}  No API keys to save.{RESET}")


def step_test_run() -> None:
    """Optional quick test."""
    print()
    if prompt_yn("Run a quick test with Hacker News?", default=True):
        print(f"\n  Running: python run_pipeline.py --dry-run --sources hackernews --no-setup\n")
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "run_pipeline.py"),
             "--dry-run", "--sources", "hackernews", "--no-setup"],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_env_key(key: str) -> str:
    """Read a single key from .env file."""
    if not ENV_PATH.exists():
        return ""
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def _write_env(api_keys: dict[str, str]) -> None:
    """Write or append API keys to .env without duplicating."""
    existing_lines: list[str] = []
    existing_keys: set[str] = set()

    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            existing_lines.append(line)
            if "=" in line and not line.startswith("#"):
                existing_keys.add(line.split("=", 1)[0].strip())

    for key, value in api_keys.items():
        if key not in existing_keys and value:
            existing_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(existing_lines) + "\n")


def _update_run_sh(tool_testing: bool) -> None:
    """Switch scheduler between digest-only and full pipeline with tool testing."""
    run_sh = PROJECT_ROOT / "scheduler" / "run.sh"
    if not run_sh.exists():
        return
    content = run_sh.read_text()
    if tool_testing:
        # Remove --digest flag so tool testing runs
        content = content.replace(
            'exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/run_pipeline.py" \\\n    --digest \\\n    --llm',
            'exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/run_pipeline.py" \\\n    --llm',
        )
    else:
        # Ensure --digest is present (skip tool testing)
        content = content.replace(
            'exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/run_pipeline.py" \\\n    --llm',
            'exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/run_pipeline.py" \\\n    --digest \\\n    --llm',
        )
    run_sh.write_text(content)


def _update_plist_time(time_str: str) -> None:
    """Update the launchd plist with a custom run time."""
    plist_path = PROJECT_ROOT / "scheduler" / "com.ainews.pipeline.plist"
    if not plist_path.exists():
        return

    hour, minute = time_str.split(":")
    content = plist_path.read_text()

    # Replace Hour value
    content = re.sub(
        r"(<key>Hour</key>\s*<integer>)\d+(</integer>)",
        rf"\g<1>{int(hour)}\2",
        content,
    )
    # Replace Minute value
    content = re.sub(
        r"(<key>Minute</key>\s*<integer>)\d+(</integer>)",
        rf"\g<1>{int(minute)}\2",
        content,
    )
    plist_path.write_text(content)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run_wizard() -> None:
    """Main wizard entry point."""
    # Check if config already exists (when run standalone)
    if CONFIG_PATH.exists():
        if not prompt_yn(f"\n{YELLOW}config.yaml already exists. Overwrite?{RESET}", default=False):
            print("  Setup cancelled.\n")
            return

    print(f"\n{'=' * 60}")
    print(f"  {BOLD}AI News Automation — First-Run Setup{RESET}")
    print(f"{'=' * 60}")
    print()
    print("  This pipeline scrapes AI news from multiple sources, ranks")
    print("  them with an LLM, optionally tests tools with a coding")
    print("  agent, and generates a daily digest.")
    print()
    print(f"  {DIM}Press Ctrl+C at any time to skip and use defaults.{RESET}")

    try:
        data: dict = {}
        data.update(step_check_deps())
        data.update(step_check_tools())
        data.update(step_llm_provider())
        data.update(step_sources())
        data.update(step_agent())
        data.update(step_distribution())
        data.update(step_telegram_voice())
        data.update(step_schedule())
        step_generate_config(data)
        step_test_run()

        print(f"\n{'=' * 60}")
        print(f"  {GREEN}{BOLD}Setup complete!{RESET}")
        print(f"{'=' * 60}")
        print(f"\n  Run the pipeline:")
        print(f"    python run_pipeline.py --dry-run          {DIM}# scrape + rank{RESET}")
        print(f"    python run_pipeline.py --dry-run --llm    {DIM}# with LLM ranking{RESET}")
        if data.get("tool_testing"):
            print(f"    python run_pipeline.py --llm              {DIM}# full run with tool testing{RESET}")
        else:
            print(f"    python run_pipeline.py --digest --llm     {DIM}# full digest{RESET}")
        print(f"\n  Re-run setup:  python -m src.setup_wizard\n")

    except KeyboardInterrupt:
        print(f"\n\n  {YELLOW}Setup cancelled.{RESET} Using defaults from config.example.yaml.")
        print(f"  Re-run setup:  python -m src.setup_wizard\n")


if __name__ == "__main__":
    run_wizard()
