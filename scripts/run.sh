#!/usr/bin/env bash
# Open the terminal app. In a new clone, this is the one command to run. Safe to run any time. Once installed,
# `lo9i` does the same from any folder (install.sh puts it on PATH).
#
# - Runs install.sh first when .env or uv is missing: it asks for the model provider and its key.
# - Then runs `lo9i`, which starts Ollama when .env points at it and builds the web UI when it's missing or older
#   than its code (scripts/prepare.sh), then opens the terminal app, which starts the daemon if it isn't running.
#   The daemon keeps running after the app exits (chat channels and scheduled work need it). Its log is
#   ~/.lo9i/logs/daemon.log.
#
# It leaves a running daemon alone, so nothing in progress stops. scripts/restart.sh puts code changes in effect.
#
# Usage: scripts/run.sh
# Env:   OLLAMA_CONTEXT_LENGTH (default 32768)
set -euo pipefail
cd "$(dirname "$0")/.."

# Where uv's installer puts it, which this shell's PATH may not have yet. Last, so a uv already on PATH wins.
export PATH="$PATH:$HOME/.local/bin"

if [[ ! -f .env ]] || ! command -v uv >/dev/null; then
  ./install.sh
fi
exec uv run --package lo9i-terminal --env-file .env lo9i
