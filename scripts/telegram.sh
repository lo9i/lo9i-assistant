#!/usr/bin/env bash
# Start the Telegram bot in the background and follow its logs.
#
# - Starts Ollama when .env points at it and it isn't running. It keeps running after this
#   script exits, because the bot needs it.
# - Starts Postgres and SearXNG, rebuilds the image, and (re)starts the bot container.
# - Ctrl+C stops following the logs; the bot keeps running.
#   Stop it with: docker compose --profile telegram stop telegram
#
# Usage: scripts/telegram.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib.sh

require_env_file
if [[ -z "$(env_value TELEGRAM_BOT_TOKEN)" ]]; then
  echo "Set TELEGRAM_BOT_TOKEN in .env (create a bot with @BotFather)." >&2
  exit 1
fi
if uses_ollama; then
  ollama_running || start_ollama >/dev/null
  check_model
fi

start_services
echo "Building the assistant image (fast when nothing changed)."
docker compose --profile telegram build telegram
docker compose --profile telegram up -d --force-recreate telegram
docker compose --profile telegram logs -f telegram
