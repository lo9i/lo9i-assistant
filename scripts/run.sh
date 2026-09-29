#!/usr/bin/env bash
# Start everything the assistant needs and open the CLI.
#
# - Starts Ollama when .env points at it (OPENAI_BASE_URL on port 11434) and it isn't running.
#   Ollama started by this script is stopped when the CLI exits.
# - Starts Postgres and SearXNG, rebuilds the image if the code changed, and runs the CLI.
#
# Usage: scripts/run.sh
# Env:   OLLAMA_CONTEXT_LENGTH (default 32768)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib.sh

started_ollama=""

stop_ollama() {
  if [[ -n "$started_ollama" ]]; then
    echo "Stopping Ollama."
    kill "$started_ollama" 2>/dev/null || true
  fi
}

require_env_file
if uses_ollama; then
  if ! ollama_running; then
    started_ollama="$(start_ollama)"
    trap stop_ollama EXIT
  fi
  check_model
fi

start_services
echo "Building the assistant image (fast when nothing changed)."
docker compose --profile cli build cli
docker compose run --rm cli
