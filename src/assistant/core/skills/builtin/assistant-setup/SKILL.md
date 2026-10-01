---
name: assistant-setup
description: How to set up and connect the assistant (email, Telegram, start at boot, its name) from the terminal app, the web UI or Telegram. Use it whenever the user asks how to configure or connect something, or a tool says something isn't set up.
---

Give the user the exact steps below for the channel in the latest turn header (`cli` is the terminal app, `web` the web UI, `telegram` Telegram). Quote commands and menu names exactly. If what they ask isn't covered here, say you don't know how rather than guessing; never describe steps as "usually" or "something like".

Where things are:

- Terminal app: slash commands typed in the message box. Typing `/` lists them.
- Web UI: http://127.0.0.1:8765/app/ on the Mac running the assistant. Settings is in the sidebar, with the tabs General and Integrations.
- Telegram: only chatting, `/new` (start a new conversation) and `/start`. Nothing can be set up from Telegram; send the user to the terminal app or the web UI.

## Email (sending)

Terminal app: `/email`. Web UI: Settings → Integrations → Email. Both start with a provider choice:

- Gmail, iCloud Mail, Yahoo Mail, AOL Mail, Fastmail: choose it, then enter only the email address and the app password. The dialog explains how to create the app password and links to the page.
- Other (enter the server yourself): SMTP host, port (587, or 465), user name (usually the full address), password (an app password for most providers), and the address to send as.
- Outlook.com / Microsoft 365: listed, but can't connect yet (it needs OAuth).

Then Connect. The assistant tries to log in right away and says whether it worked. A rejected login means a wrong user name or password (for Gmail, usually the account password instead of an app password). Other errors, such as certificate or connection errors, are problems in the assistant itself: tell the user the exact error and that it needs fixing in the assistant, and never suggest Terminal commands, installing packages or changing Python to work around it. Below the form, the user can list addresses the assistant may email without asking; the user's own address is always allowed, and anyone else needs their approval.

Getting the app password:

- Gmail: turn on 2-Step Verification in the Google Account, then create one at https://myaccount.google.com/apppasswords and paste its 16 characters without spaces. The normal Gmail password doesn't work.
- iCloud Mail: an app-specific password from https://account.apple.com (Sign-In and Security → App-Specific Passwords).
- Yahoo and AOL: an app password from the account's security settings (Generate app password).
- Fastmail: an app password from Settings → Privacy & Security.
- Outlook.com, Hotmail and Microsoft 365: not supported yet. Microsoft only allows OAuth sign-in, which the assistant can't do yet.

## Using the assistant from another computer (pairing a browser)

Every browser has to be paired once, including one on the same machine; only the terminal app on the host is trusted without it. Opening the web UI in a browser that isn't paired shows a "Pair this browser" page.

1. Create a code on a device that already uses the assistant: `/devices` → Pair a browser in the terminal app, or Settings → Devices → Pair a browser in a paired browser. The first code has to come from the terminal app on the host (directly or over SSH).
2. In the new browser, open the web UI, enter the code (it works once, for 10 minutes) and a name for the device, and press Pair.

Paired devices are listed in `/devices` and Settings → Devices, with where and when they were last used. Revoke one there (or Log out for the current browser); it then needs a new code. Too many wrong codes from one address are blocked for a few minutes.

## Telegram

Terminal app: `/telegram`. Web UI: Settings → Integrations → Telegram.

1. In Telegram, open @BotFather and send `/newbot`.
2. Choose a name, then a username ending in `bot`.
3. BotFather replies with a token like `123456789:AAH…`. Paste it into the token field and connect.
4. A pairing code appears. Open the bot in Telegram (t.me/<bot username>), press Start, and send the code. Only paired accounts can talk to the assistant.

## Start at boot

Terminal app: `/startup`. Web UI: Settings → General → Start at boot. macOS asks for the administrator password once. Afterwards the assistant runs from the moment the Mac starts, so scheduled jobs and Telegram work without anyone logged in. A sleeping or powered-off Mac runs nothing.

## The assistant's name

Terminal app: `/name <name>`. Web UI: Settings → General → Name. Or the user can just ask you to change it. The Telegram bot's display name follows it.
