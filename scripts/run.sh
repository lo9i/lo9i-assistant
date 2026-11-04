#!/usr/bin/env bash
# Open the terminal app. In a new clone, this is the one command to run. Safe to run any time.
#
# - Runs install.sh first when .env or uv is missing: it asks for the model provider and its key.
# - Starts Ollama when .env points at it (OPENAI_BASE_URL on port 11434). It keeps running.
# - Builds the web UI (clients/web/) when it's missing or older than its code.
# - Opens the terminal app, which starts the daemon if it isn't running. The daemon keeps running after
#   the app exits (chat channels and scheduled work need it). Its log is ~/.lo9i/logs/daemon.log.
#
# It leaves a running daemon alone, so nothing in progress stops. scripts/restart.sh puts code changes in effect.
#
# Usage: scripts/run.sh
# Env:   OLLAMA_CONTEXT_LENGTH (default 32768)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib.sh

# Where uv's installer puts it, which this shell's PATH may not have yet. Last, so a uv already on PATH wins.
export PATH="$PATH:$HOME/.local/bin"

if [[ ! -f .env ]] || ! command -v uv >/dev/null; then
  ./install.sh
fi
if uses_ollama; then
  ollama_running || start_ollama
  check_model
fi
if web_ui_outdated; then
  build_web_ui
fi
exec uv run --package lo9i-terminal --env-file .env lo9i
