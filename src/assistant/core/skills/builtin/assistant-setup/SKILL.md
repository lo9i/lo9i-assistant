---
name: assistant-setup
description: How to set up and connect the assistant (the model and its key, email sending, reading and new-mail alerts, Telegram, Slack, MCP servers, installing skills and MCP servers from a repository, audio, start at boot, its name) from the terminal app, the web UI, Telegram or Slack. Use it whenever the user asks how to configure or connect something, or a tool says something isn't set up.
---

Give the user the exact steps below for the channel in the latest turn header (`cli` is the terminal app, `web` the web UI, `telegram` Telegram, `slack` Slack). Quote commands and menu names exactly. If what they ask isn't covered here, say you don't know how rather than guessing; never describe steps as "usually" or "something like".

Where things are:

- Terminal app: slash commands typed in the message box. Typing `/` lists them.
- Web UI: http://127.0.0.1:8765/app/ in a browser on the computer running the assistant; from other devices, its HTTPS address (`HTTPS_HOST` and `HTTPS_PORT` in its `.env`), after pairing the browser once with a code from `/devices`. Settings is in the sidebar, with the tabs General, Integrations and Audio.
- Telegram: only chatting, `/new` (start a new conversation) and `/start`. Nothing can be set up from Telegram; send the user to the terminal app or the web UI.
- Slack: only chatting in the app's DM, and `/new` (start a new conversation). Nothing can be set up from Slack; send the user to the terminal app or the web UI.

## The model (provider and its keys)

Terminal app: `/model`. Web UI: Settings → General → Model.

1. Choose the provider. Anthropic, GitHub Copilot (a GitHub token of an account with a Copilot subscription; its model ids use dots, like `claude-opus-5.5`) and OpenAI-compatible servers (OpenAI, or another server such as Ollama, with its URL) are built in. Every other provider LangChain supports is listed too: Google Gemini and Vertex AI, Azure OpenAI and Azure AI Foundry, Amazon Bedrock, Mistral, Groq, DeepSeek, xAI, OpenRouter, Together, Fireworks, Perplexity, Cohere, NVIDIA, Upstage, Baseten, Meta, IBM watsonx, Ollama, LiteLLM and the LangSmith gateway.
2. Fill in what the provider asks for. Each shows its own fields: usually an API key; Azure an endpoint, key and API version (the model is the deployment's name); Bedrock an AWS region and access keys; Vertex AI a project, region and a service account's JSON key. Secret fields are typed only there, never in the chat.
3. The main and worker models are filled in with suggestions where there are any; otherwise type the provider's model ids. The worker model writes summaries and titles and can be cheaper.
4. Choose **Save and test**. A provider used for the first time has its package installed first, which can take a few minutes. Then each model is asked to answer once; a wrong key or model id is reported right away and nothing changes.

Saved in the app, the model overrides the one in `.env` and is used from the next message on. **Use .env instead** goes back to `.env`. To change only the models, leave the secret fields empty: the saved ones are kept. Prompt caching only works with Anthropic.

## Email (sending and reading)

Terminal app: `/email`. Web UI: Settings → Integrations → Email. The user can connect several accounts (personal, work), each with an optional name; the first one is the default, used whenever no account is named, and any other can be made the default. To add one: in the terminal, pick "Add an account" at the top; on the web, "Add an account". Both start with a provider choice:

- Gmail, iCloud Mail, Yahoo Mail, AOL Mail, Fastmail: choose it, then enter only the email address and the app password. The dialog explains how to create the app password and links to the page. The assistant can then both send and read mail.
- Other (enter the server yourself): SMTP host, port (587, or 465), user name (usually the full address), password (an app password for most providers), the address to send as, and the IMAP host for reading mail (TLS on port 993; left empty, the assistant only sends).
- Outlook.com / Microsoft 365: listed, but can't connect yet (it needs OAuth).

Then Connect. The assistant tries to log in right away and says whether it worked. A rejected login means a wrong user name or password (for Gmail, usually the account password instead of an app password). Other errors, such as certificate or connection errors, are problems in the assistant itself: tell the user the exact error and that it needs fixing in the assistant, and never suggest Terminal commands, installing packages or changing Python to work around it. Each account has its own list of addresses the assistant may email without asking; the account's own address is always allowed, and anyone else needs the user's approval. An account marked "needs sign-in" (its saved password can no longer be read) is fixed with Change sign-in. Rename changes only an account's name (unique; the assistant uses it to pick the account), without signing in again. Removing an account deletes its saved password.

Once an account can read mail, it has **New mail alerts**: Don't announce, Telegram or Slack. A short message with the account's name and the sender and subject of each new email then arrives there. For anything smarter ("tell me only when my bank writes", "summarize newsletters"), the user asks the assistant for a job that runs on new mail; jobs watch the default account. Email connected before reading existed: providers read mail automatically; with Other, connect again with the IMAP host.

Getting the app password:

- Gmail: turn on 2-Step Verification in the Google Account, then create one at https://myaccount.google.com/apppasswords and paste its 16 characters without spaces. The normal Gmail password doesn't work.
- iCloud Mail: an app-specific password from https://account.apple.com (Sign-In and Security → App-Specific Passwords).
- Yahoo and AOL: an app password from the account's security settings (Generate app password).
- Fastmail: an app password from Settings → Privacy & Security.
- Outlook.com, Hotmail and Microsoft 365: not supported yet. Microsoft only allows OAuth sign-in, which the assistant can't do yet.

## Using the assistant from another computer (pairing a browser)

Every browser has to be paired once, including one on the same machine; only the terminal app on the host is trusted without it. Opening the web UI in a browser that isn't paired shows a "Pair this browser" page.

1. Create a code on a device that already uses the assistant: `/devices` → Pair a browser in the terminal app, or Devices (in the sidebar) → Pair a browser in a paired browser. The first code has to come from the terminal app on the host (directly or over SSH).
2. In the new browser, open the web UI, enter the code (it works once, for 10 minutes) and a name for the device, and press Pair.

Paired devices are listed in `/devices` and on the Devices page in the web UI sidebar, with where and when they were last used. Revoke one there (or Log out for the current browser); it then needs a new code. Too many wrong codes from one address are blocked for a few minutes.

## Telegram

Terminal app: `/telegram`. Web UI: Settings → Integrations → Telegram.

1. In Telegram, open @BotFather and send `/newbot`.
2. Choose a name, then a username ending in `bot`.
3. BotFather replies with a token like `123456789:AAH…`. Paste it into the token field and connect.
4. A pairing code appears. Open the bot in Telegram (t.me/<bot username>), press Start, and send the code. Only paired accounts can talk to the assistant.

With Telegram connected, a scheduled job that needs approval (for example a risky command, or an email to someone not on the allowlist) sends the request there with Approve and Reject buttons, and waits up to an hour for the answer before going on without it. Without Telegram, such actions are denied and the job shows "needs attention".

## Slack

Terminal app: `/slack`. Web UI: Settings → Integrations → Slack.

1. Open https://api.slack.com/apps, choose **Create New App → From a manifest**, and pick the workspace.
2. Paste the app manifest: the **Copy manifest** button in the dialog copies it. Then choose **Next → Create**.
3. In **Basic Information → App-Level Tokens**, choose **Generate Token and Scopes**, add the scope `connections:write`, and generate. Copy the token that starts with `xapp-`.
4. In **OAuth & Permissions**, choose **Install to** the workspace, then **Allow**. The same page then shows the **Bot User OAuth Token** (`xoxb-`) and the **User OAuth Token** (`xoxp-`).
5. Paste the three tokens into the dialog and connect.
6. In Slack, open the app under **Apps** in the sidebar and send it a message. Only the person who installed the app can talk to the assistant.

The same app lets the assistant search, read and post in the workspace as the user (posting always asks first). The bot's name in Slack is set when the app is created; renaming the assistant doesn't change it.

## MCP servers (tools from other apps)

Terminal app: `/mcp`. Web UI: **MCP servers** in the sidebar.

1. Choose **Add**, give the server a short lowercase name (for example `github`), and pick how it runs:
   - **Local command**: the command that starts it, exactly as its documentation gives it (for example `npx -y @modelcontextprotocol/server-github`). Keys it needs go in **Env**, one `KEY=value` per line.
   - **Remote URL**: the server's URL. Keys it needs go in **Headers**, one `Name: value` per line (for example `Authorization: Bearer <token>`).
2. Choose **Look at tools**. The assistant connects once and lists the server's tools, all checked. Uncheck the ones the assistant shouldn't get, then choose **Add**.
3. The tools are available from the user's next message.

Keys are typed only in that dialog, never in the chat. A server is not trusted unless **Trusted** is checked: its tools that aren't marked read-only then ask for approval first, and scheduled jobs can't use them. The same screen shows whether each server is connected, and has **Save tools** (after changing the checked tools), **Trust**, **Turn off**, **Secrets** (replace the env values or headers) and **Remove**. Servers that sign in through a browser (OAuth) aren't supported yet.

## Installing plugins (MCP servers and skills)

Plugins come from the assistant's own extras (https://github.com/lo9i/lo9i-assistant-extras); there's no other source to choose.

Web UI: **Plugins** in the sidebar lists them, each installed or not, with **Install**, **Update** and **Remove**; the **+** next to Plugins (or next to MCP servers, or **Install a plugin** on the Plugins page, or **Install** on the Skills and MCP servers pages) opens the install dialog. Terminal app: `/skills` or `/mcp`, then **Install**.

1. The dialog lists what the extras offer.
2. Check the ones to install. A server that needs values (a user name, a password, a token) shows a field for each; secret ones are typed only there, never in the chat.
3. Choose **Install**. Everything is available from the user's next message.

What's installed runs on this computer. Installed servers are untrusted by default unless the extras say otherwise: their tools that aren't read-only ask for approval. **Update** downloads one again: a skill's local changes are replaced; a server keeps its values, trust and tool choices, and its data. A server can come with a page (for example Expenses): it shows up in the web UI's sidebar, for paired browsers only; the terminal app and chats can't show it. Only the user installs; you can't. When you save or delete a skill yourself, the user approves it first.

## Audio (voice messages and spoken replies)

Terminal app: `/audio`. Web UI: Settings → Audio (or `/audio` in the web chat). Both show the same settings; the microphone choice and the Try button for voices are only in the web UI.

- Speech to text: choose the model (bigger is more accurate and slower; a new model downloads with the next voice message), the transcription (Accurate weighs 5 candidate sentences; Fast takes the likeliest word each time and is about twice as fast, slightly worse on noisy audio), and the languages voice messages are detected as, then Save. On a slow computer, Fast with `tiny` or `base` answers much sooner.
- Spoken replies: Off, When I send a voice message, or Always. Choose a voice (each speaks one language) and press Try to hear it. The first spoken reply downloads the voice model (about 115 MB). Replies are spoken in the web chat and sent as Telegram voice notes, not in Slack.
- Microphone: the input this browser records with. Press the microphone button in the web chat box to record a voice message; it's sent when you press send. Recording needs the web UI on localhost or HTTPS.

## Start at boot

Terminal app: `/startup`. Web UI: Settings → General → Start at boot. Afterwards the assistant runs from the moment the computer starts, so scheduled jobs and Telegram work without anyone logged in. A sleeping or powered-off computer runs nothing.

- macOS: turning it on asks for the administrator password once.
- Linux: it installs a systemd user service, `lo9i-assistant`. To start it at boot without anyone logging in, lingering must be on; the screen says when it's off, and then an administrator runs `sudo loginctl enable-linger <user>` on that computer once. Its log: `journalctl --user -u lo9i-assistant -f`.

## The assistant's name

Terminal app: `/name <name>`. Web UI: Settings → General → Assistant → Name. Or the user can just ask you to change it. The Telegram bot's display name follows it.
