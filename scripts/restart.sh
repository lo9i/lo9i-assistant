#!/usr/bin/env bash
# Restart the daemon so code changes take effect, starting it if it isn't running.
#
# The daemon restarts once no run is in progress (daemon/restart.py), so a conversation handed to an
# agent (/claude) gets its reply first. This returns at once: an agent running it from inside a run
# would otherwise wait for itself.
#
# Usage: scripts/restart.sh
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --quiet assistant daemon restart
