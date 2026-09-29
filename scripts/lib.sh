# Shared helpers for run.sh and telegram.sh. Source from the repo root.

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

# Starts Ollama in the background and prints its pid.
start_ollama() {
  echo "Starting Ollama (log: $OLLAMA_LOG)." >&2
  OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-32768}" nohup ollama serve >"$OLLAMA_LOG" 2>&1 &
  local pid=$!
  for _ in $(seq 1 30); do
    if ollama_running; then
      echo "$pid"
      return
    fi
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

start_services() {
  docker compose up -d --wait postgres searxng
}
