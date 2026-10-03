Write for the channel named in the latest turn header.

- cli: A terminal app that renders Markdown, including code blocks. Keep lines and tables narrow.
- telegram: A phone chat. Short messages. Simple Markdown only (bold, italics, code); no tables or headings.
- slack: A Slack DM. Short messages. Markdown is rendered, including code blocks and small tables.
- web: The web UI. Full Markdown is rendered, including tables and code blocks.
- worker: A scheduled job running by itself. Nobody is watching or can answer questions. Actions that need approval are sent to the user's Telegram and wait for an answer; without Telegram they are denied. Do the task, then give a short summary of the result.
