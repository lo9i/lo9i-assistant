#!/usr/bin/env bash
# Install or update the assistant. Linux, macOS, WSL2.
#
#   curl -fsSL https://raw.githubusercontent.com/lo9i/lo9i-assistant/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/lo9i/lo9i-assistant/main/install.sh | bash -s -- --help
#
# - Piped like that, it clones the assistant into ~/lo9i-assistant (LO9I_DIR to change it; LO9I_REPO
#   to clone another repository), or updates that clone. Run from a checkout (./install.sh), it installs that checkout.
# - Installs uv when it's missing, the Python dependencies, and the web app when npm is there.
# - The first time, asks for the model provider and its key and writes .env (only on this
#   computer). Without a terminal to ask in, it writes .env from .env.example and stops.
# - Once, when Claude Code or Codex have skills on this computer, asks whether to import them into the
#   assistant's (all, pick or skip; src/lo9i/core/skills/imports/setup.py). Without a terminal it doesn't ask.
# - On Linux with systemd, runs the daemon as the systemd user service lo9i-assistant, the one
#   /startup in the app controls. Elsewhere, says how to start it.
# - Links the lo9i command into ~/.local/bin, adding that folder to PATH in the shell's profile when it isn't on
#   PATH, and installs shell completion for bash, zsh or fish (--help for the options that leave them out).
# - Run it again to update: it pulls, reinstalls and restarts. Every step is safe to repeat.
set -euo pipefail

REPO="${LO9I_REPO:-https://github.com/lo9i/lo9i-assistant.git}"
DIR="${LO9I_DIR:-$HOME/lo9i-assistant}"
SERVICE="lo9i-assistant"
SOCKET="$HOME/.lo9i/daemon.sock"
BIN="$HOME/.local/bin"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
# The PATH the user's shell has, before this script adds uv's folder to its own.
SHELL_PATH="$PATH"

DRY_RUN=0
LINK_COMMAND=1
COMPLETION=1
EDIT_PROFILES=1
# Set by --model-later: .env from .env.example, the model set in the app or brought by an import.
MODEL_LATER=0
# Set when a profile got a PATH line: the command is on PATH only in a new terminal.
PATH_ADDED=0
# The checkout being installed; in a dry run of a first install, where it would be cloned.
ROOT=""

say() { printf '%s\n' "$*" >&2; }
fail() { say "$*"; exit 1; }

usage() {
  cat <<'EOF'
Install or update lo9i, the assistant. Linux, macOS, WSL2.

Usage:
  ./install.sh [options]
  curl -fsSL https://raw.githubusercontent.com/lo9i/lo9i-assistant/main/install.sh | bash -s -- [options]

Options:
  --no-path        Don't link the lo9i command into ~/.local/bin or add that folder to PATH.
  --no-completion  Don't install shell completion.
  --skip-shell     Don't change shell profiles (.zshrc, .bashrc, .bash_profile, config.fish).
  --model-later    Don't ask for the model: it's set in the app, or comes with an import (lo9i migrate).
  --dry-run        Say what it would do, and change nothing.
  -h, --help       Show this help.

Environment:
  LO9I_DIR   Where a piped install clones lo9i (~/lo9i-assistant).
  LO9I_REPO  The repository it clones.
EOF
}

parse_args() {
  while (($#)); do
    case "$1" in
      --no-path) LINK_COMMAND=0 ;;
      --no-completion) COMPLETION=0 ;;
      --skip-shell) EDIT_PROFILES=0 ;;
      --model-later) MODEL_LATER=1 ;;
      --dry-run) DRY_RUN=1 ;;
      -h | --help) usage; exit 0 ;;
      *) say "Unknown option: $1"; usage >&2; exit 2 ;;
    esac
    shift
  done
}

# In a dry run, says what a step would do and succeeds, so `dry "..." || step` skips it; otherwise fails, so it runs.
dry() {
  ((DRY_RUN)) || return 1
  say "Would $*."
}

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
    dry "update $DIR (git pull)" || {
      say "Updating $DIR."
      git -C "$DIR" pull --ff-only --quiet
    }
    echo "$DIR"
  else
    dry "download the assistant into $DIR (git clone $REPO)" || {
      say "Downloading the assistant into $DIR."
      git clone --quiet "$REPO" "$DIR"
    }
    echo "$DIR"
  fi
}

ensure_uv() {
  command -v uv >/dev/null && return
  dry "install uv (https://docs.astral.sh/uv/)" && return
  say "Installing uv (https://docs.astral.sh/uv/)."
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null || fail "uv didn't install. Install it from https://docs.astral.sh/uv/ and run this again."
}

# --- .env -----------------------------------------------------------------------------------

ensure_env() {
  [[ -f "$ROOT/.env" ]] && return
  if ((MODEL_LATER)); then
    dry "write $ROOT/.env from .env.example, the model to be set in the app" && return
    env_from_example
    return
  fi
  dry "ask for the model provider and its key, and write $ROOT/.env" && return
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

# .env without the model's settings, which the app's Settings → Model (or an import) gives.
env_from_example() {
  cp .env.example .env.tmp
  echo "TIMEZONE=$(system_timezone)" >>.env.tmp
  chmod 600 .env.tmp
  mv .env.tmp .env
  say "Saved $PWD/.env from .env.example; the model is set in the app."
}

# Prints the provider settings for .env, asking on the terminal. Keys are read without echo.
ask_provider() {
  say ""
  say "Which model provider?"
  say "  1) Anthropic API key"
  say "  2) GitHub Copilot subscription (a GitHub token with Copilot access)"
  say "  3) OpenAI-compatible API (OpenAI, Ollama, others)"
  say "  4) OpenRouter API key (many providers' models)"
  local choice=""
  until [[ "$choice" =~ ^[1234]$ ]]; do
    read -r -p "Choice [1]: " choice </dev/tty
    choice="${choice:-1}"
  done
  case "$choice" in
    1) echo "ANTHROPIC_API_KEY=$(secret 'Anthropic API key')" ;;
    2) printf 'PROVIDER=copilot\nCOPILOT_GITHUB_TOKEN=%s\nMODEL=claude-opus-5.5\nWORKER_MODEL=claude-sonnet-5.5\n' \
         "$(secret 'GitHub token')" ;;
    3) openai_settings ;;
    4) printf 'PROVIDER=openrouter\nOPENROUTER_API_KEY=%s\nMODEL=anthropic/claude-opus-5.5\nWORKER_MODEL=anthropic/claude-sonnet-5.5\n' \
         "$(secret 'OpenRouter API key')" ;;
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

# --- Skills from other agents ---------------------------------------------------------------

# Asks once, and only when there's a terminal to ask in and skills to import.
ask_skill_imports() {
  { : </dev/tty; } 2>/dev/null || return 0
  .venv/bin/python -m lo9i.core.skills.imports.setup </dev/tty
}

# --- Starting -------------------------------------------------------------------------------

has_systemd() {
  command -v systemctl >/dev/null && systemctl --user show-environment >/dev/null 2>&1
}

start_service() {
  # The same service the app's /startup installs (src/lo9i/daemon/systemd.py).
  .venv/bin/python -m lo9i.daemon.systemd >/dev/null
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

# --- The lo9i command ------------------------------------------------------------------------

# The shell the user logs in with: bash, zsh, fish or another.
user_shell() {
  basename "${SHELL:-bash}"
}

# The profile a shell reads for each interactive terminal: macOS's terminals start bash as a login shell.
profile_of() {
  case "$1" in
    zsh) echo "${ZDOTDIR:-$HOME}/.zshrc" ;;
    bash) [[ "$(uname -s)" == Darwin ]] && echo "$HOME/.bash_profile" || echo "$HOME/.bashrc" ;;
    fish) echo "$CONFIG_HOME/fish/config.fish" ;;
  esac
}

# Adds `line` to `file` once: a profile already holding it is left as it is.
add_line() {
  local file="$1" line="$2"
  grep -qxF -- "$line" "$file" 2>/dev/null && return 0
  dry "add to $file: $line" || {
    mkdir -p "$(dirname "$file")"
    printf '\n# Added by lo9i'"'"'s install.sh\n%s\n' "$line" >>"$file"
    say "Added to $file: $line"
  }
}

# ~/.local/bin/lo9i, leading to this checkout's command. A file there that isn't a link is someone else's: left alone.
link_command() {
  local target="$ROOT/.venv/bin/lo9i" link="$BIN/lo9i"
  if [[ -e "$link" && ! -L "$link" ]]; then
    say "$link is already there and isn't a link; leaving it. The command is $target."
    return 0
  fi
  [[ -L "$link" && "$(readlink "$link")" == "$target" ]] && return 0
  dry "link $link to $target" || {
    mkdir -p "$BIN"
    ln -sfn "$target" "$link"
    say "Linked $link to $target."
  }
}

# ~/.local/bin on PATH in the shell's profile, when the shell's PATH doesn't have it.
add_to_path() {
  case ":$SHELL_PATH:" in *":$BIN:"*) return 0 ;; esac
  local shell profile
  shell="$(user_shell)"
  profile="$(profile_of "$shell")"
  if [[ -z "$profile" ]]; then
    say "Add $BIN to PATH in your shell's profile to run lo9i from any folder."
    return 0
  fi
  if [[ "$shell" == fish ]]; then
    add_line "$profile" "fish_add_path -g \"$BIN\""
  else
    add_line "$profile" "export PATH=\"$BIN:\$PATH\""
  fi
  PATH_ADDED=1
}

# Where each shell's completion goes; bash and zsh are pointed at it from their profile, fish reads its folder.
completion_file() {
  case "$1" in
    bash) echo "$DATA_HOME/bash-completion/completions/lo9i" ;;
    zsh) echo "$DATA_HOME/zsh/site-functions/_lo9i" ;;
    fish) echo "$CONFIG_HOME/fish/completions/lo9i.fish" ;;
  esac
}

install_completion() {
  local shell file
  shell="$(user_shell)"
  file="$(completion_file "$shell")"
  if [[ -z "$file" ]]; then
    say "No completion for $shell; lo9i completion bash|zsh|fish prints one."
    return 0
  fi
  dry "write the $shell completion to $file" || {
    mkdir -p "$(dirname "$file")"
    "$ROOT/.venv/bin/lo9i" completion "$shell" >"$file"
  }
  ((EDIT_PROFILES)) || return 0
  case "$shell" in
    bash) add_line "$(profile_of bash)" "[ -f \"$file\" ] && . \"$file\"" ;;
    # Only where the completion system is loaded (compinit), which defines compdef.
    zsh) add_line "$(profile_of zsh)" "(( \$+functions[compdef] )) && source \"$file\"" ;;
  esac
}

install_command() {
  if ((LINK_COMMAND)); then
    link_command
    ((EDIT_PROFILES)) && add_to_path
  fi
  ((COMPLETION)) && install_completion
  return 0
}

# How to open the chat: lo9i when it's on PATH (in a new terminal when its folder was just added).
chat_command() {
  if ((LINK_COMMAND)) && [[ -L "$BIN/lo9i" ]]; then
    case ":$SHELL_PATH:" in
      *":$BIN:"*) echo "lo9i" ;;
      *) ((PATH_ADDED)) && echo "lo9i  (in a new terminal)" || echo "$BIN/lo9i" ;;
    esac
  else
    echo "cd $ROOT && scripts/run.sh"
  fi
}

next_steps() {
  say ""
  if has_systemd; then
    say "The assistant is running. Log: ~/.lo9i/logs/daemon.log (Logs in the web app, /logs in the terminal app)"
    say "Chat in the terminal:  $(chat_command)"
  else
    say "Installed. Start it (this opens the chat, and the daemon keeps running after it):"
    say "  $(chat_command)"
    say "To start it at boot, use /startup in the chat."
  fi
  say "Check the setup: lo9i doctor. Web app: http://127.0.0.1:8765/app/ (pair the browser with /devices in the terminal chat)."
}

main() {
  parse_args "$@"
  command -v git >/dev/null || fail "git is needed. Install it and run this again."
  command -v curl >/dev/null || fail "curl is needed. Install it and run this again."
  ensure_uv
  ROOT="$(checkout)"
  # A dry run of a first install has no clone to go into; it changes nothing there anyway.
  [[ -d "$ROOT" ]] && cd "$ROOT"
  ensure_env
  # --inexact keeps the model providers' packages the daemon installed when they were chosen.
  dry "install the Python dependencies (uv sync)" || uv sync --frozen --inexact --quiet
  dry "build the web app when npm is there" || {
    source scripts/lib.sh
    build_web_ui ci
  }
  dry "ask once whether to import Claude Code's and Codex's skills" || ask_skill_imports
  if has_systemd; then
    dry "install and restart the systemd user service $SERVICE" || start_service
  fi
  install_command
  ((DRY_RUN)) && { say "Dry run: nothing was changed."; return 0; }
  next_steps
}

# Sourced (the tests), it only defines its functions; run or piped, it installs.
if [[ "${BASH_SOURCE[0]:-$0}" == "$0" ]]; then
  main "$@"
fi
