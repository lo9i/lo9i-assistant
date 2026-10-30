# Plugin checks

A plugin can check the values it's given (its fields: a token, a password, an address) when they're saved, before
they are: installing it, or changing its env or headers on the MCP page. A wrong key then shows in the dialog it was
typed in, instead of failing the plugin's first use (a coding task that fails after minutes of retries, a bot that
never answers). lo9i runs it in `core/mcp/checks.py`; installing goes on only when it passes.

It's `check:` in the plugin's `server.yaml`, one of two kinds.

## A command

```yaml
check:
  command: "{bin}/my-plugin-check"
  args: []
```

lo9i runs it as it runs the plugin's other processes: with the plugin's env (its fields as typed, a field left empty
with the value saved before), its data key, sign-in (`LO9I_OAUTH`) and lo9i's logins it asks for
(`LO9I_COPILOT_GITHUB_TOKEN`, the ssh agent), in its installed folder. Placeholders (`{bin}`, `{dir}`, `{data}`)
are filled in as in its other commands, and `{bin}` scripts come from its own environment, built before the check
runs.

- Exit 0 when the values work.
- Otherwise exit non-zero and say why on stdout, in a sentence for the user: "Telegram refused the bot token. Check
  it with @BotFather and enter it again." The apps show it as `<plugin>: <what it said>`; without anything on
  stdout, the last line it wrote on stderr. Never print a secret.

## A tool

```yaml
check:
  tool: check_account
```

A tool of the plugin's MCP server, called with no arguments on a connection of its own, started with the same env.
An error result (`isError`, such as a `ToolError` raised in it) refuses the values with its text; any other result
takes them. The agent never gets the tool and the apps don't list it, so it can say things only meant for the
user. A plugin without an MCP server (`command` or `url`) uses a command.

## What to check

Only what the values decide, as cheaply as the service allows: a call that says who the key belongs to (Telegram's
`getMe`, Anthropic's model list), signing in to the server, never a whole sync. When the service can't be reached,
or answers in a way that doesn't say the values are wrong (a rate limit, a server error), let them through: the
check is for mistakes the user can fix in the dialog, and a plugin that's offline now works once it's back.

A check has `CHECK_SECONDS` (60); one that hasn't ended by then fails. A lo9i from before checks ignores `check:`
and installs the plugin as it did, so it needs no new `format:`.
