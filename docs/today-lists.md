# Today lists

A plugin that holds part of the user's day (their calendar, bills, invoices) can list it for lo9i, which then shows it
without a model: the morning briefing, the nightly review and a Home section of that plugin read the list as the
plugin gives it, so they cost no model call and say exactly what the plugin knows. lo9i reads it in
`core/mcp/today.py`.

It's `today:` in the plugin's `server.yaml`, naming a tool of its MCP server:

```yaml
today:
  tool: today
```

Mark the tool read-only (`readOnlyHint`). lo9i calls it itself; the agent never gets it, and the apps don't list it
among the plugin's tools (its other tools read the same things). A daemon from before `today:` ignores the section and
offers the tool to the agent like any other, so it needs no new `format:`.

## The call

lo9i calls it with two arguments:

- `day`: the user's day, `YYYY-MM-DD`, in their time zone.
- `language`: the language the apps show, `en` or `es` (English for auto). Write the heading, the items' texts and
  the note in it.

## The answer

A JSON object, as the tool's structured result or as its text:

```json
{
  "heading": "Bills",
  "items": [
    {
      "title": "Electricity",
      "subtitle": "$ 61,000 · Home",
      "date": "2026-11-05",
      "time": "",
      "url": "",
      "page_path": "bills/7",
      "needs": "Pay the electricity bill ($ 61,000), due Thu 5",
      "kind": "bill due",
      "key": "expenses bill 7"
    }
  ],
  "note": ""
}
```

- `heading`: what the list is, a word or two ("Calendar", "Bills", "Invoices"). The briefing shows it above the items.
- `items`: what the user should see that day, in the order to show them, at most 30. Each is one of Home's items
  (`core/home/model.py::HomeItem`): `title`, and optionally `subtitle` (one short line: where, how much), `date`
  (`YYYY-MM-DD`; the briefing shows it when it isn't `day`), `time` (`HH:MM`, 24-hour), `url` (http or https) and
  `page_path` (its place on the plugin's page). Then, for the briefing:
  - `needs`: what the user has to do about it, a sentence that reads on its own ("Pay the electricity bill, due Thu
    5"), only when something must be done soon (a bill due within three days or overdue, invoices ready to issue).
    lo9i keeps it as an open loop, which the user closes or dismisses, and closes it itself once the plugin's list no
    longer has its `key` (the bill was paid). Empty otherwise.
  - `kind`: what kind of thing it is, in English: `calendar`, `bill due`, `invoices to issue`. The user mutes a kind of
    suggestion by it ("less of this"), and items of a muted kind are left out.
  - `key`: what it's known by across days, unique in the plugin (`expenses bill 7`), so its open loop is kept once.
- `note`: one short line when there's nothing ("No events today"), or what couldn't be read; else empty.

An error result, or an answer lo9i can't read, shows in the briefing as what couldn't be read and on the Home section
as its error, with the items it had. Answer quickly: the briefing waits for it.

## Home

A Home section of this one plugin shows its list, unless the user turns on "Use the model" in the section's editor, to
have the model build it from the section's instructions as for a plugin without a list.
