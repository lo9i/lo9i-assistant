from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Everything the daemon keeps lives under ~/.lo9i.
    database_path: str = "~/.lo9i/lo9i.db"

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

    # Model settings. MODEL and WORKER_MODEL must be ids from the chosen provider.
    # The worker gets its own model so it can run cheaper.
    # copilot: Claude and other models through a GitHub Copilot subscription (core/copilot.py),
    # with COPILOT_GITHUB_TOKEN. Model ids are Copilot's, e.g. claude-opus-4.7.
    provider: Literal["anthropic", "openai", "copilot"] = "anthropic"
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
    stt_models_dir: str = "~/.lo9i/models"

    # Single-user setup: every gateway maps to this user id.
    owner_id: str = "owner"

    # Tool groups the agent gets. See core/tools/registry.py.
    toolsets: list[str] = ["terminal", "memory", "web", "skills", "email", "slack", "jobs", "messages", "identity"]
    skills_dir: str = "~/.lo9i/skills"
    # Email bodies longer than this are cut when the agent reads them.
    email_max_chars: int = 20_000
    # MCP tool results longer than this are cut. Servers are added from the app (/mcp).
    mcp_max_output: int = 30_000

    # Scheduled jobs. A run missed while the daemon was down still runs if it's this recent.
    jobs_grace_hours: float = 6
    jobs_max_concurrent: int = 2
    jobs_timeout_minutes: int = 15
    # How long a scheduled run waits for an approval on Telegram before it's rejected. The wait
    # doesn't count toward JOBS_TIMEOUT_MINUTES.
    job_approval_minutes: int = 60

    # Web tools. metasearch queries public engines in WEB_SEARCH_ENGINES order (no key needed);
    # brave uses the Brave Search API (BRAVE_SEARCH_API_KEY).
    web_search_backend: Literal["metasearch", "brave"] = "metasearch"
    web_search_engines: str = "brave,bing,google"
    # Tried when the main backend fails. "none" disables it.
    web_search_fallback: Literal["metasearch", "brave", "none"] = "none"
    brave_search_api_key: str = ""
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
    # Uploaded attachments. Shared by every process (a Docker volume in compose).
    uploads_dir: str = "~/.lo9i/uploads"
    bash_timeout: int = 120
    bash_max_output: int = 30_000
    # always: every command. dangerous: only commands matching core/tools/bash_guard.py. never: none.
    bash_approval: Literal["always", "dangerous", "never"] = "dangerous"


settings = Settings()
