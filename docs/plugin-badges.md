# Plugin badges

A plugin with a page in the web app can show a count beside it in the sidebar: the bills due today and unpaid, say.
lo9i asks the plugin for it when the sidebar loads, and again when it may have changed; no count, or 0, shows nothing.
lo9i reads it in `core/mcp/badges.py`.

It's `badge:` in the plugin's `server.yaml`, naming a tool of its MCP server:

```yaml
badge:
  tool: badge
```

Mark the tool read-only (`readOnlyHint`). lo9i calls it itself; the agent never gets it, and the apps don't list it
among the plugin's tools (its other tools read the same things). A daemon from before `badge:` ignores the section and
offers the tool to the agent like any other, so it needs no new `format:`.

## The call

lo9i calls it with two arguments:

- `day`: the user's day, `YYYY-MM-DD`, in their time zone. Count what's of that day, not of the computer's clock.
- `language`: the language the apps show, `en` or `es` (English for auto). Write the label in it.

## The answer

A JSON object, as the tool's structured result or as its text:

```json
{ "count": 2, "label": "2 bills due today" }
```

- `count`: how many, 0 or more. 0 shows nothing.
- `label`: what the count is, a few words that read on their own; the sidebar shows it on hover and says it to screen
  readers. Empty for a generic one.

An error result, an answer lo9i can't read, or one that takes more than `BADGE_SECONDS` (10 s) shows no count, and is
logged. Answer quickly: the sidebar waits for it.

## When it's counted again

The web app asks again, with no polling, when:

- one of the plugin's tools that doesn't only read was called without an error (the assistant paid a bill);
- a request other than GET or HEAD went through the plugin's page (the user paid it there);
- the user's day ends, in their time zone (the answer says when, `next_day_in`);
- the daemon can be reached again, and the apps whose plugins count change (installed, turned on or off).

A change the plugin makes on its own, with none of these (a scheduled sync), shows on the next of them.
