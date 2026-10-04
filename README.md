# lo9i assistant

A personal AI assistant built on LangGraph. A daemon owns all state and runs the agent. You reach it from a terminal app, a web app, and chat channels installed as plugins (Telegram, Slack), and one conversation continues across them.

It remembers you (a profile, facts and past episodes), runs shell commands, searches and reads the web, sends and reads email, runs scheduled jobs, and uses tools from MCP servers. Risky actions ask for your approval first.

## Quick install

Linux, macOS, WSL2

```bash
curl -fsSL https://raw.githubusercontent.com/lo9i/lo9i-assistant/main/install.sh | bash
```

It downloads the assistant into `~/lo9i-assistant`, installs uv and the dependencies, and asks for your model provider and its key, which it saves in `.env` on that computer. On Linux it starts the assistant as a service that runs at boot; on macOS it tells you how to start it. Run it again to update.

## Requirements

- macOS or Linux
- git and curl; the installer adds [uv](https://docs.astral.sh/uv/) and Python 3.12
- Node.js, only to build the web app (without it, the web app isn't built)
- A model provider: an Anthropic API key, an OpenAI-compatible API, or a GitHub Copilot subscription

## Setup from a checkout

```bash
./install.sh            # or: cp .env.example .env, fill it in, then scripts/run.sh
```

`scripts/run.sh` builds the web app, then opens the terminal app, which starts the daemon. The daemon keeps running after the terminal app closes. Its log is `~/.lo9i/daemon.log`.

The model provider is set in the app (`/model`, or Settings → General → Model), which tests the key before saving, or in `.env`. The app's setting wins:

| Provider | Settings |
|---|---|
| Anthropic (default) | `ANTHROPIC_API_KEY` |
| OpenAI-compatible | `PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_BASE_URL` for other servers (Ollama) |
| GitHub Copilot | `PROVIDER=copilot`, `COPILOT_GITHUB_TOKEN`, and Copilot model ids (`MODEL=claude-opus-5.5`) |

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

## Running on another computer

From your development machine:

```bash
scripts/deploy.sh user@host
```

It builds the web app, copies the working tree to `~/lo9i-assistant` on the host and runs `install.sh` there. It never copies `.env`: the first time, `install.sh` writes one from `.env.example` on the host and stops, so you can fill it in and deploy again.

On Linux the daemon runs as the systemd user service `lo9i-assistant`, the same service `/startup` turns on. It starts at boot without anyone logging in only while lingering is on for that user (`sudo loginctl enable-linger <user>`, once). Its log is `journalctl --user -u lo9i-assistant -f`.

## Data

Everything the assistant keeps is in `~/.lo9i`: the database (`lo9i.db`), uploads, speech models, the bash workspace, skills and the daemon socket.

## Development

```bash
uv run ruff format && uv run ruff check && uv run pyright
uv run pytest            # offline
uv run pytest -m live    # tests that need the network or large downloads
```

For the web app, run `npm run check`, `npm test` and `npm run build` in `clients/web`. After changing an API route, run `npm run api` there to regenerate the client types.

- [`AGENTS.md`](AGENTS.md): layout, architecture rules and code rules
- [`BACKLOG.md`](BACKLOG.md): planned work
- [`clients/web/WEB.md`](clients/web/WEB.md): web app conventions
