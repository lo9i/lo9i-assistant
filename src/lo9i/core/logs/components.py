"""The areas of the assistant a log record comes from, by its logger: loggers are named after their
module (`lo9i.core.mcp.process`), so an area is the packages and modules it covers. The most
specific prefix wins. Anything else, libraries such as Hypercorn or the MCP SDK, is `OTHER`."""

OTHER = "other"

# In the order the apps list them.
_AREAS: dict[str, tuple[str, ...]] = {
    "agent": ("lo9i.core.agent",),
    "memory": ("lo9i.core.memory", "lo9i.core.conversation"),
    "model": ("lo9i.core.llm",),
    "mcp": ("lo9i.core.mcp",),
    # The channels' hub and chats, and each channel plugin's own process output (core/channels/processes.py).
    "channels": ("lo9i.core.channels",),
    "plugins": ("lo9i.core.repositories",),
    "web": ("lo9i.core.internet",),
    # Unattended runs: jobs, the mail that starts them, and their approvals forwarded to the channels.
    "scheduler": ("lo9i.daemon.scheduler", "lo9i.daemon.mail_watcher", "lo9i.core.approvals"),
    "daemon": ("lo9i.daemon",),
}

COMPONENTS = (*_AREAS, OTHER)

_PREFIXES = sorted(((p, area) for area, prefixes in _AREAS.items() for p in prefixes), key=lambda pa: -len(pa[0]))


def component_of(logger: str) -> str:
    for prefix, area in _PREFIXES:
        if logger == prefix or logger.startswith(prefix + "."):
            return area
    return OTHER
