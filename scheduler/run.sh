#!/bin/bash
# Wrapper script for launchd — loads .env and runs the pipeline.
# This is called by launchd instead of running Python directly,
# so that environment variables from .env are available.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Load .env if it exists
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Run the pipeline
if "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/run_pipeline.py" \
    --digest \
    --llm \
    2>&1; then
    RESULT=0
else
    RESULT=$?
fi

# Send macOS notification on completion
if [ $RESULT -eq 0 ]; then
    osascript -e 'display notification "Daily AI digest ready!" with title "AI News Pipeline" sound name "Glass"' 2>/dev/null || true
else
    osascript -e 'display notification "Pipeline failed — check logs" with title "AI News Pipeline" sound name "Basso"' 2>/dev/null || true
fi

exit $RESULT
