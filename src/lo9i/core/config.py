import os
from pathlib import Path
from typing import Literal
from zoneinfo import available_timezones

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def system_timezone() -> str:
    """The computer's time zone (TZ, else the /etc/localtime link), or UTC when it can't be read."""
    name = os.environ.get("TZ", "").lstrip(":")
    if not name:
        try:
            name = Path("/etc/localtime").resolve().as_posix().split("zoneinfo/", 1)[1]
        except (OSError, IndexError):
            name = ""
    return name if name in available_timezones() else "UTC"


# The checkout's .env, so `lo9i` linked onto PATH reads it from any folder, and so does the daemon it starts there; one
# in the folder it runs in goes over it.
_CHECKOUT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(_CHECKOUT_ENV, ".env"), extra="ignore")

    # Everything the daemon keeps lives under ~/.lo9i.
    database_path: str = "~/.lo9i/lo9i.db"
    # Encrypts the accounts' passwords and tokens in the database (core/secret_store.py). Kept apart
    # from it, so a copy of the database alone reveals none of them.
    secrets_key_path: str = "~/.lo9i/keys/secrets.key"

    # The daemon listens on this Unix socket and on 127.0.0.1:DAEMON_PORT.
    daemon_socket: str = "~/.lo9i/daemon.sock"
    # On macOS, the session helper listens here in the user's login session, for a daemon started at boot outside it
    # (core/login_session.py).
    session_socket: str = "~/.lo9i/session.sock"
    # While a restart or stop of the daemon waits for runs: who asked, when, and what it waits for (core/ending.py).
    restart_pending_path: str = "~/.lo9i/restart-pending.json"
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
    # openrouter: many providers' models through one OpenRouter key (core/llm/openrouter.py), with
    # OPENROUTER_API_KEY. Model ids are OpenRouter's, e.g. anthropic/claude-opus-5.5.
    provider: Literal["anthropic", "openai", "copilot", "openrouter"] = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    # Empty for OpenAI itself; another OpenAI-compatible server (Ollama: http://localhost:11434/v1).
    openai_base_url: str = ""
    copilot_github_token: str = ""
    openrouter_api_key: str = ""
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
    # Old tool results (conversation/trim.py): once the provider's prompt cache has expired
    # (llm/choice.py::prompt_cache_minutes), tool results before the last TRIM_KEEP_TURNS user turns are stubs.
    trim_keep_turns: int = 2
    # Starting a new conversation archives the old one as an episode if it had at least this many user turns.
    episode_min_turns: int = 2

    # How much long-term memory goes into the system prompt. The profile is always loaded in full; of the saved
    # facts, only the basic ones, newest first within MEMORY_BASIC_FACTS_TOKENS (core/memory/facts.py); no summary
    # of a past conversation. MEMORY_MAX_FACTS and MEMORY_MAX_EPISODES: the most recent facts and summaries the apps'
    # memory snapshot shows, and the facts the memory digest reads.
    memory_max_facts: int = 200
    memory_basic_facts_tokens: int = 300
    memory_max_episodes: int = 5
    # The other facts, and the summaries of past conversations, come into a turn when the user's message is close to
    # them in meaning (core/conversation/relevant.py): at least this cosine similarity of their E5 vectors
    # (core/memory/e5.py, which puts unrelated texts around 0.8), at most this many a message. A summary's score
    # also has to stand out from the rest by MEMORY_RELEVANT_CONVERSATIONS_MARGIN above the median of every
    # summary's, since how close all of them are moves with the message (a long one, a greeting).
    memory_relevant_facts: int = 5
    memory_relevant_similarity: float = 0.835
    memory_relevant_conversations: int = 3
    memory_relevant_conversations_similarity: float = 0.83
    memory_relevant_conversations_margin: float = 0.05

    # The assistant's persona. Used instead of the built-in one when the file exists.
    persona_path: str = "~/.lo9i/SOUL.md"
    # The user's edits of the other prompt texts they can change (core/conversation/prompt_edits.py),
    # one <name>.md each, used instead of the built-in ones.
    prompts_dir: str = "~/.lo9i/prompts"

    # Time zone for the date and time in each message's turn header. Unset: the computer's own.
    timezone: str = Field(default_factory=lambda: system_timezone())

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
    toolsets: list[str] = ["terminal", "memory", "web", "skills", "email", "jobs", "messages", "identity", "subagents"]
    # Model calls a subagent (core/subagent.py) its conversation waits for gets; one sent off in the background has
    # no limit. The last one's tool calls don't run, so it
    # answers with what it has.
    subagent_max_steps: int = 25
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
    # How long a scheduled run waits for an approval on a chat channel before it's rejected. The wait
    # doesn't count toward JOBS_TIMEOUT_MINUTES.
    job_approval_minutes: int = 60

    # Web tools. Without a Brave Search API key (set in the app, core/internet/brave_key.py), search
    # queries public engines through ddgs: "auto" for every engine ddgs has enabled, or a list
    # such as "yahoo,duckduckgo". With a key, they're a fallback when Brave fails. Free search services
    # (core/internet/keyless.py) come after them.
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
    # Where an agent a conversation is handed to (/claude) works when the user picks no project.
    agent_workspace_dir: str = "~/.lo9i/claude-workspace"
    # What the user typed in the terminal app, for Up and Down.
    cli_history_path: str = "~/.lo9i/cli_history"
    cli_history_limit: int = 1000
    # Preferences changed from inside the terminal app, such as /mouse. Kept by the client.
    cli_preferences_path: str = "~/.lo9i/cli_preferences.json"
    # Uploaded attachments. Messages keep only a reference to the file here.
    uploads_dir: str = "~/.lo9i/uploads"
    # The daemon's log files (core/logs/), and the output of a daemon started in the background.
    logs_dir: str = "~/.lo9i/logs"
    bash_timeout: int = 120
    bash_max_output: int = 30_000
    # always: every command. dangerous: only commands matching core/tools/bash_guard.py. never: none.
    bash_approval: Literal["always", "dangerous", "never"] = "dangerous"


settings = Settings()
