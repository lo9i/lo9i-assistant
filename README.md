# lo9i assistant

**Your own AI assistant, running on your computer.** Chat with it from Telegram, WhatsApp, Slack, the web or the terminal, and it handles your email, calendar, bills, servers and code. It remembers you across all of them.

Works with an Anthropic key, an OpenRouter key, any OpenAI-compatible API (including Ollama), or **just a GitHub Copilot subscription**.

![lo9i web app](https://lo9i.com.ar/img/web-delegate.webp)

Website: [lo9i.com.ar](https://lo9i.com.ar/) · MIT licensed

## What it can do

- **One assistant everywhere:** terminal app, web app, Telegram, Slack and WhatsApp; a conversation continues across them
- **Memory:** a profile of you, saved facts and past conversations
- **Email and calendar:** read, search and send mail, new-mail alerts, CalDAV and macOS calendars
- **Life admin:** bills and due dates, a movie/TV watchlist with downloads, YouTube videos and transcripts
- **Your servers:** run commands on your Linux hosts in a shared terminal, with SSH tunnels
- **Coding:** hand tasks to Claude Code, or to the *factory*, where several models debate the spec and plan before an agent builds it on a branch
- **Scheduled jobs:** "every morning, send me what's due this week"
- **Safe by default:** risky actions ask for your approval first; secrets stay in the daemon
- **Extensible:** everything is a plugin, built on MCP

## Quick install

Linux, macOS, WSL2

```bash
curl -fsSL https://raw.githubusercontent.com/lo9i/lo9i-assistant/main/install.sh | bash
```

It downloads the assistant into `~/lo9i-assistant`, installs uv and the dependencies, and asks for your model provider and its key, which it saves in `.env` on that computer. It links the `lo9i` command into `~/.local/bin` (adding that folder to PATH in your shell's profile when it isn't there) and installs its completion for bash, zsh or fish. On Linux it starts the assistant as a service that runs at boot; on macOS it tells you how to start it. Run it again to update.

`--dry-run` says what it would do and changes nothing; `--no-path`, `--no-completion` and `--skip-shell` (no shell profile changed) leave those parts out. Piped, pass them after `bash -s --`:

```bash
curl -fsSL https://raw.githubusercontent.com/lo9i/lo9i-assistant/main/install.sh | bash -s -- --help
```

## The lo9i command

| Command | What it does |
|---|---|
| `lo9i` | Opens the chat in the terminal, starting the daemon if it isn't running (and Ollama, when `.env` points at it; the web app is built first when its code changed) |
| `lo9i doctor` | Checks the setup: the daemon answering, the model's key, each plugin, email accounts, chat channels, the web app built, free disk space and the command on PATH, each with a fix. It works while the daemon is down too; `--json` prints it as JSON, and it exits with 1 when something fails. The apps show the same under Settings → Health (Check setup) |
| `lo9i daemon` | Runs the daemon in the foreground; `lo9i daemon restart` restarts the running one once no reply is in progress |
| `lo9i completion bash\|zsh\|fish` | Prints the shell completion script |

## Requirements

- macOS or Linux
- git and curl; the installer adds [uv](https://docs.astral.sh/uv/) and Python 3.12
- Node.js, only to build the web app (without it, the web app isn't built)
- A model provider: an Anthropic API key, an OpenRouter API key, an OpenAI-compatible API, or a GitHub Copilot subscription

## Setup from a checkout

```bash
git clone https://github.com/lo9i/lo9i-assistant.git
cd lo9i-assistant
scripts/run.sh
```

The first run installs what's missing and asks for your model provider and its key. After that, `scripts/run.sh` opens the terminal app as `lo9i` does, building the web app first only when its code changed. The terminal app starts the daemon if it isn't running, and the daemon keeps running after the app closes, so the web app stays up at http://127.0.0.1:8765/app/.

`scripts/run.sh` never restarts a running daemon. After pulling or changing code, run `scripts/restart.sh`, which restarts it once no reply is in progress.

The daemon's log is `~/.lo9i/logs/daemon.log` (Logs in the web app, `/logs` in the terminal app). A crash before logging starts is in `~/.lo9i/logs/output.log`, shown there as `output`.

The model provider is set in the app (`/model`, or Settings → General → Model), which tests the key before saving, or in `.env`. The app's setting wins:

| Provider | Settings |
|---|---|
| Anthropic (default) | `ANTHROPIC_API_KEY` |
| OpenAI-compatible | `PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_BASE_URL` for other servers (Ollama) |
| GitHub Copilot | `PROVIDER=copilot`, `COPILOT_GITHUB_TOKEN`, and Copilot model ids (`MODEL=claude-opus-5.5`) |
| OpenRouter | `PROVIDER=openrouter`, `OPENROUTER_API_KEY`, and OpenRouter model ids (`MODEL=anthropic/claude-opus-5.5`) |

Other settings are listed in `.env.example`.

## Connecting things

Everything else is set up from inside the app, not in `.env`. Secrets are typed in dialogs and stay in the daemon.

| What | Terminal app | Web app |
|---|---|---|
| The model (provider, key, models) | `/model` | Settings → General |
| Telegram, Slack (install the plugin, then set it up in its details) | `/plugins` | Settings → Plugins |
| Email (send and read, new-mail alerts): install the provider's plugin, then add accounts in its details | `/plugins` | Settings → Plugins |
| MCP servers | `/mcp` | MCP servers |
| Start at boot | `/startup` | Settings → General |
| Browsers on other computers | `/devices` | Devices |

Type `/` in the terminal app to list every command. You can also ask the assistant how to set something up.

The web app is served by the daemon at http://127.0.0.1:8765/app/. A browser must be paired with a one-time code from `/devices` before it can use the assistant. For access from other computers, set the `HTTPS_*` settings in `.env`.

## Plugins

Plugins live in [lo9i-assistant-extras](https://github.com/lo9i/lo9i-assistant-extras) and install from the app (`/plugins`, or Settings → Plugins). To write your own, see [`docs/agent-plugins.md`](docs/agent-plugins.md) and [`docs/channel-plugins.md`](docs/channel-plugins.md). New plugins are welcome.

## For developers

### Running on another computer

From your development machine:

```bash
scripts/deploy.sh user@host
```

It builds the web app, copies the working tree to `~/lo9i-assistant` on the host and runs `install.sh` there. It never copies `.env`: the first time, `install.sh` writes one from `.env.example` on the host and stops, so you can fill it in and deploy again.

On Linux the daemon runs as the systemd user service `lo9i-assistant`, the same service `/startup` turns on. It starts at boot without anyone logging in only while lingering is on for that user (`sudo loginctl enable-linger <user>`, once). Its log is `~/.lo9i/logs/daemon.log`, as on macOS; a crash before logging starts is in `journalctl --user-unit lo9i-assistant`, which the Logs page shows as `output`.

### Data

Everything the assistant keeps is in `~/.lo9i`: the database (`lo9i.db`), uploads, speech models, the bash workspace, skills and the daemon socket.

### Development

```bash
uv run ruff format && uv run ruff check && uv run pyright
uv run pytest            # offline
uv run pytest -m live    # tests that need the network or large downloads
```

For the web app, run `npm run check`, `npm test` and `npm run build` in `clients/web`. After changing an API route, run `npm run api` there to regenerate the client types.

- [`AGENTS.md`](AGENTS.md): layout, architecture rules and code rules
- [`BACKLOG.md`](BACKLOG.md): planned work
- [`clients/web/WEB.md`](clients/web/WEB.md): web app conventions

## License

[MIT](LICENSE).
