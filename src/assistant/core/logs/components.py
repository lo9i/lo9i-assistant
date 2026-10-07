"""The areas of the assistant a log record comes from, by its logger: loggers are named after their
module (`assistant.core.mcp.process`), so an area is the packages and modules it covers. The most
specific prefix wins. Anything else, libraries such as uvicorn or the MCP SDK, is `OTHER`."""

OTHER = "other"

# In the order the apps list them.
_AREAS: dict[str, tuple[str, ...]] = {
    "agent": ("assistant.core.agent",),
    "memory": ("assistant.core.memory", "assistant.core.conversation"),
    "model": ("assistant.core.llm",),
    "mcp": ("assistant.core.mcp",),
    "plugins": ("assistant.core.repositories",),
    "web": ("assistant.core.internet",),
    # Unattended runs: jobs, the mail that starts them, and their approvals forwarded to the channels.
    "scheduler": ("assistant.daemon.scheduler", "assistant.daemon.mail_watcher", "assistant.core.approvals"),
    "daemon": ("assistant.daemon",),
}

COMPONENTS = (*_AREAS, OTHER)

_PREFIXES = sorted(((p, area) for area, prefixes in _AREAS.items() for p in prefixes), key=lambda pa: -len(pa[0]))


def component_of(logger: str) -> str:
    for prefix, area in _PREFIXES:
        if logger == prefix or logger.startswith(prefix + "."):
            return area
    return OTHER
