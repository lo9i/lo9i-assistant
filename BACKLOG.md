# Backlog

Open work, tackled one at a time. Finished items are deleted and the remaining codes renumbered. Items waiting
for something to happen before they're worth doing are under To revisit, with what brings them back.
A = action, L = to revisit later, G = memory gap, H = context improvement, Q = open question, R = risk.

## Agent

- A32. A view of all background subagents across conversations (`core/background_subagents/`): today each shows only in its conversation's side panel (web app) and `/subagents` (terminal app). The API already lists them all (`GET /subagents` without `thread_id`), and `subagents` events carry each one's conversation.

## Daemon

- A10. Passkeys as a faster sign-in for devices paired over the network (HTTPS and device pairing are done: `daemon/auth.py`, `daemon/https.py`).
- A11. Spending limits on the token ledger (`core/usage`): per job run, per job per day, per conversation and overall per day. Checked before every model call; going over ends the run cleanly (a job run is recorded as over budget, a chat gets a clear message), and a warning at a threshold (80%) goes to Telegram or Slack.
- A12. The journal reader (`core/logs/journal.py`) is tested only against a fake `journalctl`. Check on the Linux host that `journalctl --user-unit lo9i-assistant` run as the daemon's user reads the service's output and systemd's notes about it, whatever the journal's storage there.
- A13. On macOS a daemon started by hand while start at boot is on can't be stopped from the apps (`launchd.Beside` refuses): launchd keeps trying to start the LaunchDaemon, and stopping its tries needs an administrator. Ask for the password, as turning start at boot on does, and stop them.
- A14. Pinning conversations to Home (`core/home/pins.py`, `PUT`/`DELETE /home/pins/<id>`) is only in the web app: the terminal app shows the Conversations card's result in `/home` but can't pin or unpin (the Python `DaemonClient` has `home.pin` and `home.unpin`), and that result, built by code (`core/home/conversations.py`), is built again only when a pin changes or Home refreshes, so its times lag behind the conversations; the web app draws the card live. Add pinning to the terminal app's conversation list, and build the card again on `conversations` events while a client shows Home.

## Plugins

- A15. Calls (the phone plugin) and anything else that opens an app need lo9i in the user's login session: from boot (`/startup`, a LaunchDaemon) `open` has no screen. Run the daemon as a LaunchAgent in the user's session on macOS, or keep a helper there for what needs the screen. It would also give plugins that ask for the ssh agent (`ssh_agent: true`, `core/mcp/ssh_agent.py`) the user's agent, which a LaunchDaemon has none of.

## Voice

- A16. Real-time voice agent: live spoken conversation from the browser.
  - A speech-to-speech model (OpenAI GPT-Live) listens and speaks. No separate speech-to-text or text-to-speech step; transcripts come from the model's own events.
  - Audio goes directly between the browser and OpenAI over WebRTC. The daemon only exchanges the connection offer and answer, and never handles audio.
  - The daemon keeps a sideband WebSocket to OpenAI for each call. When the voice model needs to act, it calls a tool; the daemon runs it through `AssistantService`, so Claude stays the brain.
  - Tool calls are logged by the model's call id, so a retried call returns the first result.
  - Needs an OpenAI key in addition to the Anthropic key. Not needed for Telegram voice notes.

## Platforms

- A17. Windows. Nothing runs there today: the terminal app reaches the daemon only through a Unix socket (`client/connection.py`), and `/startup` knows only launchd and systemd (`daemon/startup.py`).
  - Daemon connection: a named pipe or localhost with a paired device instead of the Unix socket.
  - Startup: a Task Scheduler task or a Windows service as a `daemon/startup.py` backend.
  - Clipboard: `client/clipboard/windows.py`, pasting files, images and text with PowerShell (`Get-Clipboard -Format FileDropList`, `System.Windows.Forms.Clipboard.GetImage`) and copying with `Set-Clipboard`.
  - Bash tool, data paths and `install.sh`: decide between native Windows and running under WSL.

## To revisit

Not worth doing yet; each item says what was done and when to look at it again.

- L1. Plugins repeat the code their protocol needs: Telegram and Slack each have `daemon.py` and `runner.py`, Claude Code and Copilot each have `task_folder.py`, so a protocol change means changing every copy. Done: the extras' `tests/test_shared_code.py` (run by their pre-commit hook) fails when the copies differ, and lists the differences meant to be there. Left: publish one small client per protocol on PyPI, which each plugin's `uv.lock` pins. Revisit when a third channel or agent plugin comes, or a protocol changes again.
- L2. Try NVIDIA Nemotron 3.5 Transcribe (open, 40 languages incl. Spanish, speaker labels, translation, questions about a recording, term hints in the prompt, up to 1 h of audio) in place of faster-whisper, or as a plugin for long recordings such as meetings or YouTube videos without captions. Today it's 30B (4B active) and only runs on a large NVIDIA GPU via vLLM; hosted APIs (DeepInfra, Baseten) send audio to a third party. Revisit when its quantized versions and NeMo-Speech.cpp ship and it runs on a Mac. https://huggingface.co/blog/nvidia/nemotron-transcribe-granary
- L3. The Copilot agent's context bar (extras, `assistant/agents/copilot`, `usage.py`) was written from the CLI's code and tried only against fakes: this computer's Copilot access is restricted. On an account with Copilot, check that the CLI (1.0.95) writes `--usage-output-file` with `currentModel` and `lastCallInputTokens` in `-p` mode, that a fine-grained token with Copilot Requests reads `api.github.com/copilot_internal/user` and its API's `/models` (with `Copilot-Integration-Id: copilot-developer-cli`), and that the bar shows once a task ends. It shows only then: the CLI writes its usage when it's done.
- L4. OpenRouter (`core/llm/openrouter.py`) is tested only against a fake API; no call has been made with a real key. Check on one: a streamed reply with tool calls, and a reasoning model's tool round (Claude with reasoning on, Gemini, GPT) taking its `reasoning_details` back. Its prompt caching is OpenRouter's default: models that cache on their own (OpenAI, DeepSeek, Gemini) do, but Anthropic's need `cache_control` breakpoints, which nothing sends, so a Claude model there pays its whole input on every call; add them as the Anthropic builder does, and `prompt_cache_minutes` for it. Home's refresh (`core/home/refresh.py::_expected`) tells usage limits and outages apart only for OpenAI's errors, not OpenRouter's SDK errors (nor Anthropic's). Its models have no cost in the usage report until `MODEL_PRICES` sets one (`core/usage/prices.py`), though its model list gives each model's prices.
- L5. Checks and Google Contacts were tried only against fakes: the claude-code plugin's check with a real Claude token from `claude setup-token` (it lists Anthropic's models with the token as a bearer and the `oauth-2025-04-20` beta; a 401 there refuses it, so if that list doesn't take sign-in tokens the check refuses good ones) and with a real API key; the contacts plugin on a real Google account (the `https://www.googleapis.com/auth/carddav` scope, the CardDAV API turned on, discovery from `/.well-known/carddav`).
- L6. Model connections that notice when they died (`core/llm/connections.py`, TCP keepalive) still miss the LangChain providers whose packages make their clients in private code (`core/llm/kept_alive.py` says which and why: Anthropic on Bedrock and on Bedrock Mantle, NVIDIA, Google Gemini, Vertex AI, IBM watsonx, LiteLLM), and Anthropic's own reach them only through `core/llm/claude.py`, which replaces langchain-anthropic's private `_async_client`. Give them those connections, and drop claude.py's override, once their packages take a client, a transport or socket options. Revisit when one of those packages takes a client, a transport or socket options.

## Open questions and risks

- R1. Bash runs on the host as the daemon's user. It can read `~/.lo9i` (including the database with the Telegram token, the email password and MCP servers' keys) and that user's other files. Only dangerous-command approvals stand in the way. With remote access (A10), a stolen paired device can reach this too until it's revoked. A paired device can also add a local MCP server, which runs its command without approval. Options: run the daemon as a dedicated user with little else on the host, and run just the bash tool in a sandbox container.
- R2. MCP servers send text the model reads (tool descriptions and results). Hidden Unicode tag characters are stripped and write tools on untrusted servers need approval, but visible injected instructions still reach the model. A server whose tool list keeps changing starts a new epoch at each message (a prompt cache miss each time). A server also names the conversation its finished background work is told to by sending back the call's `_meta["lo9i/origin"]` (`core/mcp/background.py`), which isn't signed: it can put a note in any conversation whose id it learned from a call.
- R3. langchain-openrouter 0.2.9 takes only the openrouter SDK below 1.0, and the SDK's 0.11 releases take only pydantic below 2.13, so the lock holds the SDK at 0.10.8 to keep pydantic where it is (`uv lock --upgrade-package "pydantic==<version>"` when it's added). `uv lock --upgrade` would move pydantic back to 2.12 for it. Revisit when langchain-openrouter takes the SDK 1.x (which takes pydantic below 3).
- R4. The folder panel beside a conversation not handed to an agent reads the whole home folder (`GET /folders/home`, `.../file`) and deletes any file in it the tree shows once deleting is turned on in Settings → General (`DELETE /folders/home/file`, off by default), hiding only what the agent folder's panel hides (.git, node_modules, .venv, what git ignores): a paired device can preview `~/.ssh` keys, `~/.lo9i/keys/secrets.key` with `~/.lo9i/lo9i.db` (every secret `core/secret_store.py` keeps), cloud credentials. Through chat it could already have the agent read them (R1), but this needs no model and no approval. Decide what the home folder leaves out (lo9i's data folder, its keys, known credential folders, or hidden files unless asked, as the /claude folder picker does) and whether its file previews and deletions should need the device to be on the Unix socket or confirmed.
- Langfuse: run the self-hosted stack and set keys.
