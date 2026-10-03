#!/usr/bin/env bash
# Install the assistant on this Linux host and run its daemon as a systemd user service
# (lo9i-assistant), started at boot. Run again after updating the code: it reinstalls the
# dependencies and restarts the daemon.
#
# - Needs uv, and a .env next to this checkout (copy .env.example and fill it in). The .env stays
#   on this host; nothing here writes credentials.
# - The service runs as the current user, and /startup in the app shows and controls it. Starting
#   at boot without logging in needs lingering: the script says how to turn it on when it's off
#   (it needs sudo once).
# - The daemon log: journalctl --user -u lo9i-assistant -f
#
# Usage: scripts/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib.sh

SERVICE="lo9i-assistant"
SOCKET="$HOME/.lo9i/daemon.sock"

require_linux() {
  if ! command -v systemctl >/dev/null; then
    echo "This script installs a systemd service, so it needs Linux. On macOS, use /startup in the app." >&2
    exit 1
  fi
  command -v uv >/dev/null || { echo "uv isn't installed: https://docs.astral.sh/uv/" >&2; exit 1; }
}

check_linger() {
  if [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]]; then
    echo "Note: lingering is off, so the daemon only runs while $USER is logged in." >&2
    echo "      To start it at boot: sudo loginctl enable-linger $USER" >&2
  fi
}

# The daemon answers /health on its Unix socket once it's ready.
wait_until_ready() {
  for _ in $(seq 1 60); do
    if curl -sf --unix-socket "$SOCKET" http://lo9i/health >/dev/null 2>&1; then
      echo "The daemon is running. Log: journalctl --user -u $SERVICE -f"
      return
    fi
    sleep 1
  done
  echo "The daemon didn't answer within a minute. Log: journalctl --user -u $SERVICE -n 50" >&2
  exit 1
}

require_linux
require_env_file
uv sync --frozen
# The same service the app's /startup installs (src/assistant/daemon/systemd.py).
.venv/bin/python -m assistant.daemon.systemd >/dev/null
systemctl --user restart "$SERVICE"
check_linger
wait_until_ready
