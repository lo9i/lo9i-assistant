#!/usr/bin/env bash
# Install or update the assistant. Linux, macOS, WSL2.
#
#   curl -fsSL https://raw.githubusercontent.com/lo9i/lo9i-assistant/main/install.sh | bash
#
# - Piped like that, it clones the assistant into ~/lo9i-assistant (LO9I_DIR to change it; LO9I_REPO
#   to clone another repository), or updates that clone. Run from a checkout (./install.sh), it installs that checkout.
# - Installs uv when it's missing, the Python dependencies, and the web app when npm is there.
# - The first time, asks for the model provider and its key and writes .env (only on this
#   computer). Without a terminal to ask in, it writes .env from .env.example and stops.
# - On Linux with systemd, runs the daemon as the systemd user service lo9i-assistant, the one
#   /startup in the app controls. Elsewhere, says how to start it.
# - Run it again to update: it pulls, reinstalls and restarts.
set -euo pipefail

REPO="${LO9I_REPO:-https://github.com/lo9i/lo9i-assistant.git}"
DIR="${LO9I_DIR:-$HOME/lo9i-assistant}"
SERVICE="lo9i-assistant"
SOCKET="$HOME/.lo9i/daemon.sock"

say() { printf '%s\n' "$*" >&2; }
fail() { say "$*"; exit 1; }

# The checkout this script runs from, or "" when it was piped.
own_checkout() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd || true)"
  [[ -n "$here" && -f "$here/pyproject.toml" && -f "$here/scripts/lib.sh" ]] && echo "$here" || true
}

checkout() {
  local own
  own="$(own_checkout)"
  if [[ -n "$own" ]]; then
    echo "$own"
  elif [[ -d "$DIR/.git" ]]; then
    say "Updating $DIR."
    git -C "$DIR" pull --ff-only --quiet
    echo "$DIR"
  else
    say "Downloading the assistant into $DIR."
    git clone --quiet "$REPO" "$DIR"
    echo "$DIR"
  fi
}

ensure_uv() {
  command -v uv >/dev/null && return
  say "Installing uv (https://docs.astral.sh/uv/)."
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null || fail "uv didn't install. Install it from https://docs.astral.sh/uv/ and run this again."
}

# --- .env -----------------------------------------------------------------------------------

ensure_env() {
  [[ -f .env ]] && return
  # Opening /dev/tty fails without a terminal (ssh host cmd, CI), even when its permissions allow it.
  if ! { : </dev/tty; } 2>/dev/null; then
    cp .env.example .env
    chmod 600 .env
    fail "Created $PWD/.env from .env.example. Set the model provider and its key there, then run this again."
  fi
  ask_provider >.env.tmp
  echo "TIMEZONE=$(system_timezone)" >>.env.tmp
  chmod 600 .env.tmp
  mv .env.tmp .env
  say "Saved $PWD/.env. More settings are listed in .env.example."
}

# Prints the provider settings for .env, asking on the terminal. Keys are read without echo.
ask_provider() {
  say ""
  say "Which model provider?"
  say "  1) Anthropic API key"
  say "  2) GitHub Copilot subscription (a GitHub token with Copilot access)"
  say "  3) OpenAI-compatible API (OpenAI, Ollama, others)"
  local choice=""
  until [[ "$choice" =~ ^[123]$ ]]; do
    read -r -p "Choice [1]: " choice </dev/tty
    choice="${choice:-1}"
  done
  case "$choice" in
    1) echo "ANTHROPIC_API_KEY=$(secret 'Anthropic API key')" ;;
    2) printf 'PROVIDER=copilot\nCOPILOT_GITHUB_TOKEN=%s\nMODEL=claude-opus-5.5\nWORKER_MODEL=claude-sonnet-5.5\n' \
         "$(secret 'GitHub token')" ;;
    3) openai_settings ;;
  esac
}

openai_settings() {
  local url model
  read -r -p "Base URL (empty for OpenAI; Ollama: http://localhost:11434/v1): " url </dev/tty
  read -r -p "Model id: " model </dev/tty
  echo "PROVIDER=openai"
  echo "OPENAI_API_KEY=$(secret 'API key (any text for Ollama)')"
  [[ -n "$url" ]] && echo "OPENAI_BASE_URL=$url"
  printf 'MODEL=%s\nWORKER_MODEL=%s\n' "$model" "$model"
}

# Asks until something is typed: it runs in $(...), where failing wouldn't stop the script.
secret() {
  local value=""
  until [[ -n "$value" ]]; do
    read -r -s -p "$1: " value </dev/tty
    say ""
  done
  echo "$value"
}

system_timezone() {
  local zone=""
  command -v timedatectl >/dev/null && zone="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
  [[ -z "$zone" && -L /etc/localtime ]] && zone="$(readlink /etc/localtime | sed 's|.*/zoneinfo/||')"
  echo "${zone:-UTC}"
}

# --- Starting -------------------------------------------------------------------------------

has_systemd() {
  command -v systemctl >/dev/null && systemctl --user show-environment >/dev/null 2>&1
}

start_service() {
  # The same service the app's /startup installs (src/assistant/daemon/systemd.py).
  .venv/bin/python -m assistant.daemon.systemd >/dev/null
  systemctl --user restart "$SERVICE"
  if [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]]; then
    say "Note: lingering is off, so the assistant only runs while $USER is logged in."
    say "      To start it at boot: sudo loginctl enable-linger $USER"
  fi
  wait_until_ready
}

# The daemon answers /health on its Unix socket once it's ready.
wait_until_ready() {
  for _ in $(seq 1 60); do
    curl -sf --unix-socket "$SOCKET" http://lo9i/health >/dev/null 2>&1 && return
    sleep 1
  done
  fail "The daemon didn't answer within a minute. Log: journalctl --user -u $SERVICE -n 50"
}

next_steps() {
  say ""
  if has_systemd; then
    say "The assistant is running. Log: journalctl --user -u $SERVICE -f"
    say "Chat in the terminal:  cd $PWD && uv run --package assistant-terminal assistant"
  else
    say "Installed. Start it (this opens the chat, and the daemon keeps running after it):"
    say "  cd $PWD && scripts/run.sh"
    say "To start it at boot, use /startup in the chat."
  fi
  say "Web app: http://127.0.0.1:8765/app/ (pair the browser with /devices in the terminal chat)."
}

main() {
  command -v git >/dev/null || fail "git is needed. Install it and run this again."
  command -v curl >/dev/null || fail "curl is needed. Install it and run this again."
  ensure_uv
  cd "$(checkout)"
  source scripts/lib.sh
  ensure_env
  uv sync --frozen --quiet
  build_web_ui
  has_systemd && start_service
  next_steps
}

main "$@"
