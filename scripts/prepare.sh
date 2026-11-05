#!/usr/bin/env bash
# What opening the chat needs besides the daemon, run by `lo9i` (clients/terminal/src/lo9i_terminal/main.py) before
# it opens the terminal app. Safe to run any time.
#
# - Starts Ollama when .env points at it (OPENAI_BASE_URL on port 11434). It keeps running.
# - Builds the web UI (clients/web/) when it's missing or older than its code.
#
# Env:   OLLAMA_CONTEXT_LENGTH (default 32768)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib.sh

if [[ -f .env ]] && uses_ollama; then
  ollama_running || start_ollama
  check_model
fi
if web_ui_outdated; then
  build_web_ui
fi
