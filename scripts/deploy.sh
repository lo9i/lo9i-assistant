#!/usr/bin/env bash
# Install or update the assistant on another (Linux) host over SSH, from this checkout.
#
# - Builds the web UI here, so the host doesn't need npm.
# - Copies this working tree, including uncommitted changes, to DIR on the host. The host's .env,
#   virtualenv and data (~/.lo9i) are left alone.
# - Runs scripts/install.sh there, which installs the dependencies and (re)starts the daemon as a
#   systemd user service. The first time, create DIR/.env on the host before running this
#   (copy .env.example), or the install stops and says so.
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
ssh "$HOST" "$DIR/scripts/install.sh"
