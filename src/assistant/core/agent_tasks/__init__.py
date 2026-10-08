"""Tasks handed to a coding agent a plugin brings (`agent:` in its server.yaml, docs/agent-plugins.md):
Claude Code, Copilot. The daemon keeps each task's records in the plugin's data folder (records.py),
starts the plugin's worker for it detached, so it outlives a restart of the daemon (workers.py), and
follows what the worker writes (waiting.py). The agent gets tools to start and follow tasks (tools.py),
and a conversation handed to the agent runs each message as a task (service.py, `converse`)."""
