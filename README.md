# AI News Pipeline

A daily automated pipeline that scrapes AI news from multiple sources, ranks them with an LLM, optionally tests tools with a coding agent, and generates digests.

**Sources:** Hacker News, Reddit, GitHub Trending, RSS feeds, Product Hunt, YouTube, Twitter/X

**Features:**
- 🔄 Scrapes from 7 news sources in parallel
- 🧠 LLM ranking (Ollama/LM Studio/Anthropic/OpenAI)
- 🤖 Optional tool testing with Claude Code or OpenCode
- 📊 Daily digest generation
- 📱 Obsidian integration
- 🚀 GitHub publishing
- 📅 macOS launchd scheduler (daily automation)
- 🎯 Interactive first-run setup wizard

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/7ucid7ibra/ai-news-pipeline.git
cd ai-news-pipeline
```

### 2. Check Python Version

**Requirement:** Python 3.12 or higher

```bash
python3 --version
```

If you have an older version, install Python 3.14 or 3.13:

**macOS (with Homebrew):**
```bash
brew install python@3.14
```

Then resolve the actual Homebrew path (works on both Apple Silicon and Intel Macs):
```bash
PY314="$(brew --prefix python@3.14)/bin/python3.14"
"$PY314" --version
```

On Apple Silicon this is typically `/opt/homebrew/bin/python3.14`.
On Intel Macs this is typically `/usr/local/bin/python3.14`.

### 3. Create Virtual Environment

Using Python 3.12+:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

If you installed a specific version via Homebrew, use its full path:
```bash
PY314="$(brew --prefix python@3.14)/bin/python3.14"
rm -rf .venv
"$PY314" -m venv .venv
source .venv/bin/activate
```

Your prompt should now show `(.venv)`.

Confirm you're using the venv interpreter:
```bash
python -V
python -c "import sys; print(sys.executable)"
```

### 4. Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

This installs:
- Core: `anthropic`, `requests`, `feedparser`, `praw`, `pyyaml`, `rapidfuzz`
- Optional: `yt-dlp` (YouTube), `playwright` (Twitter scraping)

**Verify installation:**
```bash
python -c "import yaml; print('OK')"
```

### 5. Deactivate the Virtual Environment

When you're done, exit the venv with:

```bash
deactivate
```

---

## Quick Start

### First Run (Interactive Setup)

Activate the virtual environment first:
```bash
source .venv/bin/activate
```

```bash
python run_pipeline.py
```

The wizard will guide you through:
1. ✅ Python dependency checks
2. 🔧 Optional tools (yt-dlp, ollama, claude CLI)
3. 🧠 LLM provider selection (auto-detects Ollama, LM Studio, or API keys)
4. 📰 News source selection
5. 📁 Distribution options (Obsidian, GitHub)
6. ⏰ Daily schedule setup
7. 🧪 Quick test run

This generates `config.yaml` and `.env` automatically.

### Subsequent Runs

Activate the virtual environment first:
```bash
source .venv/bin/activate
```

Scrape + basic ranking:
```bash
python run_pipeline.py --dry-run
```

Scrape + rank with LLM:
```bash
python run_pipeline.py --dry-run --llm
```

Full pipeline: scrape, rank, digest (no testing):
```bash
python run_pipeline.py --digest --llm
```

Full pipeline: scrape, rank, test, distribute:
```bash
python run_pipeline.py --llm
```

---

## Configuration

After setup, edit `config.yaml` to customize:

- **Sources:** Enable/disable news sources
- **LLM provider:** `ollama`, `lmstudio`, `anthropic`, or `openai`
- **Schedule time:** Daily run time (e.g., `06:00`)
- **Distribution:** GitHub repo, Obsidian vault paths
- **Testing:** Max tools to test, timeout

**Re-run setup anytime:**
```bash
python -m src.setup_wizard
```

---

## LLM Providers

### Ollama (Recommended for Local)

Free, runs entirely on your machine.

**Install:**
```bash
brew install ollama
ollama serve &
```

**In another terminal, pull a model:**
```bash
ollama pull llama3.1
```

The pipeline will auto-detect Ollama running on `localhost:11434`.

### LM Studio

Another free local option with a UI.

**Download:** https://lmstudio.ai

Start the server (default port: 1234). The pipeline auto-detects it.

### Anthropic (Claude)

**Set API key:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or add to `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### OpenAI (GPT)

**Set API key:**
```bash
export OPENAI_API_KEY="sk-..."
```

Or add to `.env`:
```
OPENAI_API_KEY=sk-...
```

---

## Optional: Tool Testing

The pipeline can install and test recommended tools (Stage 3).

**Requires either:**
- Claude Code CLI: `npm install -g @anthropic-ai/claude-code`
- OpenCode CLI: https://opencode.ai/docs/

**Run with testing:**
```bash
python run_pipeline.py --llm
```

To skip testing and just generate a digest:
```bash
python run_pipeline.py --digest --llm
```

---

## Optional: Daily Automation (macOS)

Install the scheduler to run the pipeline automatically each morning:

```bash
bash scheduler/install.sh install
```

This:
- Creates a launchd agent
- Runs daily at 6:00 AM (configurable)
- Logs to `logs/`
- Sends macOS notifications on success/failure

**Manage the scheduler:**
```bash
bash scheduler/install.sh status      # Check if running
bash scheduler/install.sh run-now     # Trigger immediately
bash scheduler/install.sh uninstall   # Remove scheduler
```

---

## Uninstall / Cleanup

If you're testing on a separate Mac and want to remove everything:

### 1. Uninstall Scheduler (if installed)
```bash
bash scheduler/install.sh uninstall
```

### 2. Deactivate Virtual Environment (if active)
```bash
deactivate
```

### 3. Remove Local Python Environment and Generated Data
Run from the project root:
```bash
rm -rf .venv data output logs
rm -f config.yaml .env
```

### 4. (Optional) Remove Editable Package from User Site
```bash
pip uninstall -y ai-news-automation
```

### 5. (Optional) Remove the Repository Folder Entirely
From the parent directory:
```bash
rm -rf ai-news-pipeline
```

---

## Usage Examples

### Scrape Only
```bash
python run_pipeline.py --dry-run --sources hackernews reddit
```

### Test a Single Source
```bash
python run_pipeline.py --dry-run --sources hackernews --llm
```

### Specify LLM Provider
```bash
python run_pipeline.py --llm --provider ollama --model mistral
python run_pipeline.py --llm --provider anthropic
python run_pipeline.py --llm --provider opencode
```

### Specify Agent for Tool Testing
```bash
python run_pipeline.py --llm --agent opencode
python run_pipeline.py --llm --agent claude
```

### Test Only Top 3 Tools
```bash
python run_pipeline.py --llm --max-test 3
```

### Output as JSON
```bash
python run_pipeline.py --dry-run --json > results.json
```

### Run for a Specific Date
```bash
python run_pipeline.py --date 2026-03-01 --dry-run --llm
```

### Skip Setup Wizard
```bash
python run_pipeline.py --dry-run --no-setup
```

---

## Troubleshooting

### Python Version Error
```
TypeError: 'NoneType' object is not callable
```

**Solution:** You're using Python < 3.12. Install Python 3.14:
```bash
brew install python@3.14
PY314="$(brew --prefix python@3.14)/bin/python3.14"
rm -rf .venv
"$PY314" -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### `ModuleNotFoundError: No module named 'yaml'`

**Cause:** `pip` and `python` may be pointing to different environments.

**Solution:** Re-activate the venv, verify interpreter path, and install with `python -m pip`:
```bash
source .venv/bin/activate
python -V
python -c "import sys; print(sys.executable)"
python -m pip install --upgrade pip
python -m pip install -e .
```

Verify:
```bash
python -c "import yaml; print('OK')"
```

### `zsh: command not found: python`

Use `python3`, or activate the virtual environment first:
```bash
source .venv/bin/activate
python run_pipeline.py
```

Without venv:
```bash
python3 run_pipeline.py
```

### `No LLM provider available`

The pipeline tried Ollama, LM Studio, and API keys but found none.

**Solutions:**
1. Install Ollama: https://ollama.com
2. Install LM Studio: https://lmstudio.ai
3. Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env`

The pipeline will auto-detect and use the first available.

### `yt-dlp not found`

YouTube scraper is optional. Install if needed:
```bash
pip install yt-dlp
```

### Scheduler Not Working

**Check status:**
```bash
bash scheduler/install.sh status
```

**View logs:**
```bash
tail -f logs/launchd-stdout.log
```

**Reinstall:**
```bash
bash scheduler/install.sh uninstall
bash scheduler/install.sh install
```

### Permission Denied When Writing Config

Make sure the project directory is writable:
```bash
chmod u+w .
```

---

## Project Structure

```
ai-news-pipeline/
├── run_pipeline.py           # Main entry point
├── config.example.yaml       # Config template
├── pyproject.toml            # Python dependencies
├── src/
│   ├── scrapers/             # 7 news source scrapers
│   ├── pipeline/             # Aggregation + ranking
│   ├── agent/                # Tool testing + evaluation
│   ├── distribute/           # Digest + GitHub + Obsidian
│   ├── config.py             # Config loader
│   ├── models.py             # Data models
│   └── setup_wizard.py       # Interactive setup
├── scheduler/                # macOS launchd config
└── README.md                 # This file
```

---

## Contributing

Found a bug? Have a suggestion? Open an issue or PR on GitHub.

---

## License

MIT

---

## Quick Command Reference

Setup:
```bash
source .venv/bin/activate
python run_pipeline.py
python -m src.setup_wizard
```

Scraping:
```bash
python run_pipeline.py --dry-run
python run_pipeline.py --dry-run --llm
```

Full pipeline:
```bash
python run_pipeline.py --digest --llm
python run_pipeline.py --llm
```

With options:
```bash
python run_pipeline.py --llm --provider ollama --agent opencode
python run_pipeline.py --dry-run --sources hackernews --llm
```

Automation:
```bash
bash scheduler/install.sh install
bash scheduler/install.sh status
bash scheduler/install.sh run-now
```
