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

    # Single-user setup: every gateway maps to this user id.
    owner_id: str = "owner"

    # Tool groups the agent gets. See core/tools/registry.py.
    toolsets: list[str] = ["terminal", "memory"]

    workspace_dir: str = "workspace"
    # Uploaded attachments. Shared by every process (a Docker volume in compose).
    uploads_dir: str = "~/.lo9i/uploads"
    bash_timeout: int = 120
    bash_max_output: int = 30_000
    # always: every command. dangerous: only commands matching core/tools/bash_guard.py. never: none.
    bash_approval: Literal["always", "dangerous", "never"] = "dangerous"


settings = Settings()
