# Opening apps from a plugin

On macOS a plugin may need the user's screen: the phone plugin opens the Phone app with a `tel:` link, and another
one might open an app or a page there. A process can only do that from the user's login session. When lo9i runs in
the session (started by hand, or by the terminal app), a plugin's processes are in it too and `open` just works. When
it starts at boot (`/startup`, a LaunchDaemon, `daemon/launchd.py`), it runs before anyone logs in and outside the
session: `open` fails there, as there's no screen to show anything on.

For that case lo9i installs the session helper with start at boot: a LaunchAgent (`daemon/session_agent.py`) that
launchd runs in the user's session while they're logged in (`python -m assistant.session`, `src/assistant/session/`).
It opens links and apps for the plugins that ask, and links the session's ssh agent for the plugins that ask for the
agent (`ssh_agent: true`), which a daemon from boot has none of (`core/mcp/ssh_agent.py`).

## Asking for it

```yaml
login_session: true
```

in the plugin's `server.yaml`. Its processes (its MCP server, page, channel, agent worker and check) then get
`LO9I_LOGIN_SESSION`, the path of the helper's Unix socket, while lo9i runs outside the session. While it runs in the
session they don't get it: the plugin opens what it needs itself, with `open`. The install dialogs say the plugin opens
apps on the screen.

## The protocol

Connect to the socket, write one JSON object on a line, read one back; one request per connection.

```json
{"op": "open", "url": "tel:+5491112345678"}
{"op": "open", "url": "https://example.com", "app": "Safari"}
{"op": "open", "app": "Music"}
```

The helper runs `open` with the link, the app (`open -a`) or both, and answers `{"ok": true}`, or `{"error": "..."}`
with why it didn't: `open`'s own words, or that it doesn't take what was asked. It takes only links with a scheme
(`tel:`, `https:`, `facetime:`...), never `file:` nor a path, which could run a script, and an app by its name.

When nothing answers on the socket (the connection is refused, or the socket isn't there), nobody is logged in on the
Mac, or the helper is starting: say so, as in "Nobody is logged in on the Mac: the Phone app opens on its screen, so log
in and try again." Wait at most a few seconds for an answer.

```python
import asyncio, json, os

async def open_in_session(url: str) -> None:
    reader, writer = await asyncio.open_unix_connection(os.environ["LO9I_LOGIN_SESSION"])
    writer.write(json.dumps({"op": "open", "url": url}).encode() + b"\n")
    await writer.drain()
    answer = json.loads(await asyncio.wait_for(reader.readline(), 15))
    writer.close()
    if "error" in answer:
        raise RuntimeError(answer["error"])
```

The helper also answers `{"op": "version"}` and `{"op": "quit"}`, for the daemon: at its start it has a helper running
older code quit, and launchd starts it again with the code installed now.
