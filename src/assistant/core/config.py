from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://assistant:assistant@localhost:5433/assistant"

    # Model settings. MODEL and WORKER_MODEL must be ids from the chosen provider.
    # The worker gets its own model so it can run cheaper.
    provider: Literal["anthropic", "openai"] = "anthropic"
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

    # How much long-term memory goes into the system prompt. The profile is always loaded in full.
    memory_max_facts: int = 200
    memory_max_episodes: int = 5

    # The assistant's persona. Used instead of the built-in one when the file exists.
    persona_path: str = "~/.lo9i/SOUL.md"

    # Time zone for the date and time in each message's turn header.
    timezone: str = "UTC"

    # Telegram gateway. Only these Telegram user ids may use the bot.
    telegram_bot_token: str = ""
    telegram_allowed_user_ids: list[int] = []

    # Single-user setup: every gateway maps to this user id.
    owner_id: str = "owner"

    # Tool groups the agent gets. See core/tools/registry.py.
    toolsets: list[str] = ["terminal", "memory", "web"]

    # Web tools. SEARXNG_URL points at the compose service inside Docker.
    web_search_backend: Literal["searxng", "brave", "duckduckgo"] = "searxng"
    # Tried when the main backend fails. "none" disables it.
    web_search_fallback: Literal["searxng", "brave", "duckduckgo", "none"] = "duckduckgo"
    brave_search_api_key: str = ""
    searxng_url: str = "http://localhost:8888"
    web_blocked_domains: list[str] = []
    web_cache_minutes: int = 20
    web_extract_max_chars: int = 20_000

    workspace_dir: str = "workspace"
    # Uploaded attachments. Shared by every process (a Docker volume in compose).
    uploads_dir: str = "~/.lo9i/uploads"
    bash_timeout: int = 120
    bash_max_output: int = 30_000
    # always: every command. dangerous: only commands matching core/tools/bash_guard.py. never: none.
    bash_approval: Literal["always", "dangerous", "never"] = "dangerous"


settings = Settings()
