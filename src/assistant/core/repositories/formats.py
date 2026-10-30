"""Which version of the plugin format a server.yaml is written in: `format:`, 1 when it declares none.
A plugin written in a newer format than this daemon reads uses something it doesn't know (a placeholder,
a section), so it's handled as one for another system (repositories/platforms.py): not found in the
repository, so it isn't listed, offered, installed or updated here until lo9i is updated."""

from assistant.core.i18n import said

# 2: `{bin}`, the scripts of the plugin's own environment (core/mcp/environment.py).
# 3: an agent's `worker`, run by the daemon for each task (docs/agent-plugins.md).
# 4: `data_key`, a key of the plugin's own for encrypting its data (core/mcp/data_key.py).
# 5: `oauth`, signing in with the user's own OAuth app (core/mcp/plugin_oauth.py).
# 6: `subagent`, a named subagent the assistant delegates tasks to (core/mcp/subagents.py).
# 7: `approve`, tools that ask the user before each call even on a trusted server (core/mcp/servers.py): a
#    daemon that didn't know it would run them without asking.
CURRENT = 7


def parse(value: object) -> int:
    """Raises ValueError for anything but a whole number from 1."""
    if value is None:
        return 1
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(said("its format must be a whole number from 1"))
    return value


def readable(version: int) -> bool:
    return version <= CURRENT
