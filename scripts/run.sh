#!/usr/bin/env bash
# Start what the assistant depends on, then open the chat.
#
# - Starts Ollama when .env points at it (OPENAI_BASE_URL on port 11434). It keeps running.
# - Stops a running daemon, so code changes take effect.
# - Opens the CLI, which starts the daemon if it isn't running. The daemon keeps running after
#   the CLI exits (Telegram and scheduled work need it). Its log is ~/.lo9i/daemon.log.
#
# Usage: scripts/run.sh
# Env:   OLLAMA_CONTEXT_LENGTH (default 32768)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib.sh

require_env_file
if uses_ollama; then
  ollama_running || start_ollama
  check_model
fi

stop_daemon
uv run --env-file .env assistant
