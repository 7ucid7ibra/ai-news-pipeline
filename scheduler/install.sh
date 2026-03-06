#!/bin/bash
# Install/uninstall the AI News Pipeline launchd scheduler
# Usage:
#   ./scheduler/install.sh install    # Install and start
#   ./scheduler/install.sh uninstall  # Stop and remove
#   ./scheduler/install.sh status     # Check if running
#   ./scheduler/install.sh run-now    # Trigger immediately

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_NAME="com.ainews.pipeline"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

case "${1:-help}" in
    install)
        echo "Installing AI News Pipeline scheduler..."

        # Check prerequisites
        if [ ! -f "$PROJECT_DIR/.venv/bin/python" ]; then
            echo "Error: Virtual environment not found. Run: python3 -m venv .venv && pip install -e ."
            exit 1
        fi

        if [ ! -f "$PROJECT_DIR/.env" ] && [ ! -f "$PROJECT_DIR/config.yaml" ]; then
            echo "Warning: No .env or config.yaml found. Copy .env.example to .env and add your API keys."
        fi

        # Create logs directory
        mkdir -p "$PROJECT_DIR/logs"

        # Generate plist with correct paths
        sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$PLIST_SRC" > "$PLIST_DEST"

        # Load the agent
        launchctl unload "$PLIST_DEST" 2>/dev/null || true
        launchctl load "$PLIST_DEST"

        echo "Installed! Pipeline will run daily at 6:00 AM."
        echo "  Plist: $PLIST_DEST"
        echo "  Logs:  $PROJECT_DIR/logs/"
        echo ""
        echo "To run immediately: $0 run-now"
        echo "To change schedule: edit $PLIST_SRC and re-run $0 install"
        ;;

    uninstall)
        echo "Uninstalling AI News Pipeline scheduler..."
        launchctl unload "$PLIST_DEST" 2>/dev/null || true
        rm -f "$PLIST_DEST"
        echo "Removed."
        ;;

    status)
        if launchctl list | grep -q "$PLIST_NAME"; then
            echo "Status: LOADED"
            launchctl list "$PLIST_NAME" 2>/dev/null || true
        else
            echo "Status: NOT LOADED"
        fi

        # Show last run
        if [ -f "$PROJECT_DIR/logs/launchd-stdout.log" ]; then
            echo ""
            echo "Last output (tail):"
            tail -5 "$PROJECT_DIR/logs/launchd-stdout.log"
        fi
        ;;

    run-now)
        echo "Triggering pipeline now..."
        launchctl kickstart "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || \
            launchctl start "$PLIST_NAME" 2>/dev/null || \
            echo "Agent not loaded. Run: $0 install"
        echo "Check logs: tail -f $PROJECT_DIR/logs/launchd-stdout.log"
        ;;

    help|*)
        echo "AI News Pipeline Scheduler"
        echo ""
        echo "Usage: $0 {install|uninstall|status|run-now}"
        echo ""
        echo "  install    Install launchd agent (runs daily at 6 AM)"
        echo "  uninstall  Remove launchd agent"
        echo "  status     Check if scheduler is running"
        echo "  run-now    Trigger the pipeline immediately"
        ;;
esac
