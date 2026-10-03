"""The daemon: the only process that holds state and runs the agent. Clients (CLI, web) talk to it
over HTTP on a Unix socket or localhost; channel adapters (Telegram, Slack) run inside it."""
