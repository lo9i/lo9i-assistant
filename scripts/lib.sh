# Shared helpers for the run scripts. Source from the repo root.

OLLAMA_URL="http://localhost:11434"
OLLAMA_LOG="${TMPDIR:-/tmp}/lo9i-ollama.log"

env_value() {
  grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true
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

# Builds the web UI into the daemon package (src/lo9i/daemon/webui), which serves it at /app/.
# Without npm the build is skipped and /app/ says the page isn't built; the CLI still works.
# `build_web_ui ci` installs the packages exactly as package-lock.json has them, never rewriting it: in a clone the
# app updates, a changed lock would stop every later update (src/lo9i/daemon/updates.py). Without it, a
# checkout someone works in installs as usual, keeping node_modules and the lock in line with package.json.
build_web_ui() {
  if ! command -v npm >/dev/null; then
    echo "npm isn't installed; skipping the web UI build." >&2
    return
  fi
  echo "Building the web app." >&2
  npm --prefix clients/web "${1:-install}" --no-audit --no-fund --silent
  local log
  log="$(mktemp)"
  if ! npm --prefix clients/web run build --silent >"$log"; then
    cat "$log" >&2
    rm -f "$log"
    echo "The web app didn't build." >&2
    exit 1
  fi
  rm -f "$log"
}

# Whether the web UI is missing or older than any of the files it's built from.
web_ui_outdated() {
  local built=src/lo9i/daemon/webui/_app/version.json
  [[ ! -f "$built" ]] && return 0
  [[ -n "$(find clients/web/src clients/web/static clients/web/package.json clients/web/package-lock.json \
    clients/web/svelte.config.js clients/web/vite.config.ts -type f -newer "$built" -print -quit)" ]]
}
