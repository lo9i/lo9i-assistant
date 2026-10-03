#!/usr/bin/env bash
# Install or update the assistant on another (Linux) host over SSH, from this checkout.
#
# - Builds the web UI here, so the host doesn't need npm.
# - Copies this working tree, including uncommitted changes, to DIR on the host. The host's .env,
#   virtualenv and data (~/.lo9i) are left alone.
# - Runs install.sh there, which installs the dependencies and (re)starts the daemon as a systemd
#   user service. The first time, without a terminal to ask in, it writes DIR/.env from
#   .env.example and stops: fill it in on the host and deploy again.
#
# Usage: scripts/deploy.sh user@host [DIR]   (DIR defaults to lo9i-assistant, in the user's home)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib.sh

HOST="${1:?Usage: scripts/deploy.sh user@host [DIR]}"
DIR="${2:-lo9i-assistant}"

build_web_ui
rsync -az --delete \
  --exclude .venv --exclude .env --exclude workspace --exclude .idea \
  --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
  --exclude clients/web/node_modules --exclude clients/web/.svelte-kit \
  ./ "$HOST:$DIR/"
ssh "$HOST" "$DIR/install.sh"
