# Shared helpers for the run scripts. Source from the repo root.

OLLAMA_URL="http://localhost:11434"
OLLAMA_LOG="${TMPDIR:-/tmp}/lo9i-ollama.log"

env_value() {
  grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true
}

require_env_file() {
  if [[ ! -f .env ]]; then
    echo "Missing .env. Copy .env.example to .env and fill it in." >&2
    exit 1
  fi
}

uses_ollama() {
  [[ "$(env_value OPENAI_BASE_URL)" == *":11434"* ]]
}

ollama_running() {
  curl -sf "$OLLAMA_URL/api/tags" >/dev/null
}

# Starts Ollama in the background; it keeps running for the daemon.
start_ollama() {
  echo "Starting Ollama (log: $OLLAMA_LOG)." >&2
  OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-32768}" nohup ollama serve >"$OLLAMA_LOG" 2>&1 &
  for _ in $(seq 1 30); do
    ollama_running && return
    sleep 1
  done
  echo "Ollama didn't start. See $OLLAMA_LOG." >&2
  exit 1
}

check_model() {
  local model
  model="$(env_value MODEL)"
  if ! ollama list | awk 'NR > 1 {print $1}' | grep -qx "$model"; then
    echo "Model $model isn't downloaded. Run: ollama pull $model" >&2
    exit 1
  fi
}

# Stops a running daemon so the next start picks up code changes: SIGTERM first (clean shutdown),
# SIGKILL if it hasn't exited after 10 seconds. A daemon started at boot (/startup) is restarted by
# systemd, and by launchd when its LaunchDaemon dates from before the daemon could be stopped from the
# app; the CLI then uses whichever daemon answers first. A newer LaunchDaemon leaves it stopped after a
# clean exit, so the CLI starts its own.
stop_daemon() {
  local pids
  pids="$(pgrep -f -- "-m assistant.daemon" || true)"
  [[ -z "$pids" ]] && return
  echo "Stopping the running daemon (pid $(echo $pids | tr '\n' ' '))." >&2
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 20); do
    pgrep -f -- "-m assistant.daemon" >/dev/null || return
    sleep 0.5
  done
  echo "The daemon didn't stop in time; killing it." >&2
  pkill -9 -f -- "-m assistant.daemon" || true
}

# Builds the web UI into the daemon package (src/assistant/daemon/webui), which serves it at /app/.
# Without npm the build is skipped and /app/ says the page isn't built; the CLI still works.
build_web_ui() {
  if ! command -v npm >/dev/null; then
    echo "npm isn't installed; skipping the web UI build." >&2
    return
  fi
  npm --prefix clients/web install --no-audit --no-fund --silent
  npm --prefix clients/web run build --silent >/dev/null
}
