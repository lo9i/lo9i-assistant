from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Everything the daemon keeps lives under ~/.lo9i.
    database_path: str = "~/.lo9i/lo9i.db"
    # Encrypts the accounts' passwords and tokens in the database (core/secret_store.py). Kept apart
    # from it, so a copy of the database alone reveals none of them.
    secrets_key_path: str = "~/.lo9i/keys/secrets.key"

    # The daemon listens on this Unix socket and on 127.0.0.1:DAEMON_PORT.
    daemon_socket: str = "~/.lo9i/daemon.sock"
    daemon_port: int = 8765
    # Browsers on other hosts: HTTPS on HTTPS_BIND:HTTPS_PORT with this certificate and key, for
    # the name HTTPS_HOST (e.g. assistant.example.com). Off while HTTPS_PORT is 0. Every network
    # request, this one or the localhost port, needs a paired device (/devices); only the Unix
    # socket doesn't.
    https_port: int = 0
    https_bind: str = "0.0.0.0"
    https_host: str = ""
    https_cert: str = ""
    https_key: str = ""

    # Model settings, used until the provider is set in the app (Settings → Model, /model), which
    # then overrides them (core/llm/choice.py). MODEL and WORKER_MODEL must be ids from the chosen
    # provider; the worker gets its own model so it can run cheaper.
    # copilot: Claude and other models through a GitHub Copilot subscription (core/llm/copilot.py),
    # with COPILOT_GITHUB_TOKEN. Model ids are Copilot's, e.g. claude-opus-5.5.
    provider: Literal["anthropic", "openai", "copilot"] = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    # Empty for OpenAI itself; another OpenAI-compatible server (Ollama: http://localhost:11434/v1).
    openai_base_url: str = ""
    copilot_github_token: str = ""
    model: str = "claude-opus-5-5"
    worker_model: str = "claude-opus-5-5"
    effort: str = "medium"
    max_tokens: int = 16000
    # Anthropic only: effort above, and server_fallbacks below.
    # Retry refused requests on a substitute model. Supported on Opus 5.5, Opus 5,
    # Fable 5.1 and Sonnet 5.5 (Claude API only). Turn off for other models.
    server_fallbacks: bool = True

    # Epochs (compaction). A new epoch starts when the current one passes the size limit
    # or after an idle gap. On a size limit, the last EPOCH_KEEP_TURNS user turns are kept.
    epoch_max_tokens: int = 150_000
    epoch_idle_hours: float = 6
    epoch_keep_turns: int = 4
    # Starting a new conversation archives the old one as an episode if it had at least this many user turns.
    episode_min_turns: int = 2

    # How much long-term memory goes into the system prompt. The profile is always loaded in full.
    memory_max_facts: int = 200
    memory_max_episodes: int = 5

    # The assistant's persona. Used instead of the built-in one when the file exists.
    persona_path: str = "~/.lo9i/SOUL.md"

    # Time zone for the date and time in each message's turn header.
    timezone: str = "UTC"

    # Speech to text (faster-whisper on the CPU). Detection is limited to STT_LANGUAGES.
    # Models: tiny, base, small, medium, large-v3-turbo. Downloaded on first use.
    stt_model: str = "small"
    stt_languages: list[str] = ["es", "en"]
    # accurate: beam search over 5 candidates. fast: one candidate (greedy), about twice as fast
    # on a slow CPU, slightly worse on noisy or unclear audio.
    stt_decoding: Literal["accurate", "fast"] = "accurate"
    stt_models_dir: str = "~/.lo9i/models"
    # The embedding model memory search uses (core/memory/e5.py).
    embedding_models_dir: str = "~/.lo9i/models"

    # Single-user setup: every gateway maps to this user id.
    owner_id: str = "owner"

    # Tool groups the agent gets. See core/tools/registry.py.
    # Prices per million tokens for models without built-in ones (core/usage/prices.py), as JSON:
    # MODEL_PRICES='{"gpt-5": {"input": 1.25, "output": 10, "cache_read": 0.125}}'. Overrides them too.
    model_prices: dict[str, dict[str, float]] = {}
    toolsets: list[str] = ["terminal", "memory", "web", "skills", "email", "slack", "jobs", "messages", "identity"]
    skills_dir: str = "~/.lo9i/skills"
    # Email bodies longer than this are cut when the agent reads them.
    email_max_chars: int = 20_000
    # MCP tool results longer than this are cut. Servers are added from the app (/mcp).
    mcp_max_output: int = 30_000
    # Code of MCP servers installed from a repository, one folder each.
    mcp_dir: str = "~/.lo9i/mcp"
    # Data of MCP servers installed from a repository, one folder each. Kept when a server is updated
    # or removed.
    mcp_data_dir: str = "~/.lo9i/data"

    # Scheduled jobs. A run missed while the daemon was down still runs if it's this recent.
    jobs_grace_hours: float = 6
    jobs_max_concurrent: int = 2
    jobs_timeout_minutes: int = 15
    # How long a scheduled run waits for an approval on Telegram before it's rejected. The wait
    # doesn't count toward JOBS_TIMEOUT_MINUTES.
    job_approval_minutes: int = 60

    # Web tools. Without a Brave Search API key (set in the app, core/internet/brave_key.py), search
    # queries public engines through ddgs: "auto" for every engine ddgs has enabled, or a list
    # such as "yahoo,duckduckgo". With a key, they're the fallback when Brave fails.
    web_search_engines: str = "auto"
    web_blocked_domains: list[str] = []
    web_cache_minutes: int = 20
    web_extract_max_chars: int = 20_000
    # Pages with less text than this after download are rendered in a headless browser,
    # installed automatically into BROWSERS_DIR by the daemon.
    web_render: bool = True
    web_render_min_chars: int = 300
    browsers_dir: str = "~/.lo9i/browsers"

    workspace_dir: str = "~/.lo9i/workspace"
    # What the user typed in the terminal app, for Up and Down.
    cli_history_path: str = "~/.lo9i/cli_history"
    cli_history_limit: int = 1000
    # Preferences changed from inside the terminal app, such as /mouse. Kept by the client.
    cli_preferences_path: str = "~/.lo9i/cli_preferences.json"
    # Uploaded attachments. Messages keep only a reference to the file here.
    uploads_dir: str = "~/.lo9i/uploads"
    bash_timeout: int = 120
    bash_max_output: int = 30_000
    # always: every command. dangerous: only commands matching core/tools/bash_guard.py. never: none.
    bash_approval: Literal["always", "dangerous", "never"] = "dangerous"


settings = Settings()
