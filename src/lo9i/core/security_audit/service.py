"""The parts of the security audit that read the daemon's state: the devices paired to reach it over the network, the
setup code while it's open, and the plugins and MCP servers that run commands here. Pure: the daemon gathers what
they read (core/agent/security_audit.py)."""

from datetime import datetime, timedelta

from lo9i.core.devices import UNUSED_LIFETIME, Device
from lo9i.core.i18n import said
from lo9i.core.mcp.servers import McpServer
from lo9i.core.repositories.known import EXTRAS
from lo9i.core.setup_check.model import SetupCheck

# A device unused this long is likely one nobody uses any more; it stops working by itself at UNUSED_LIFETIME.
IDLE = timedelta(days=30)
_REVOKE = said("Revoke it in Settings → Devices (/devices in the terminal app) unless you still use it.")
_PLUGIN_FIX = said("Remove it in Settings → Plugins (/plugins) unless you know what it runs.")


def no_devices() -> SetupCheck:
    detail = said("None paired: only this computer's apps reach the daemon.")
    return SetupCheck("devices", said("Paired devices"), "ok", detail)


def device(found: Device, now: datetime) -> SetupCheck:
    """A paired device: when it was paired and last used, and from where; one unused for `IDLE` warns."""
    unused = now - datetime.fromisoformat(found.last_used_at)
    detail = said(
        "Paired {paired}, last used {days} days ago from {ip}.",
        paired=found.created_at[:10],
        days=unused.days,
        ip=found.last_ip or "?",
    )
    title = said("Device {name}", name=found.name)
    if unused >= UNUSED_LIFETIME:
        return SetupCheck(f"device:{found.id}", title, "ok", said("Expired: it has to pair again."))
    if unused >= IDLE:
        return SetupCheck(f"device:{found.id}", title, "warn", detail, _REVOKE)
    return SetupCheck(f"device:{found.id}", title, "ok", detail)


def setup_code(open_: bool, exposed: bool) -> SetupCheck | None:
    """While no device was ever paired, whoever has the setup code pairs first; it matters where other computers
    reach the daemon (`exposed`). None once it's closed."""
    if not open_:
        return None
    title = said("Setup code")
    if not exposed:
        return SetupCheck("setup_code", title, "ok", said("Open, but no port is open to other computers."))
    detail = said("Open: the first browser that types it pairs, from any computer reaching the HTTPS port.")
    return SetupCheck("setup_code", title, "warn", detail, said("Pair your own browser now, which closes it."))


def runs_here(server: McpServer) -> bool:
    """Whether an enabled server starts a process on this computer: its MCP server, page, channel or agent worker."""
    return server.enabled and bool(_commands(server))


def plugin(server: McpServer) -> SetupCheck:
    """A plugin or MCP server that runs commands here: what it runs, where it came from, and what it's given."""
    detail = said("Runs {commands}; {origin}", commands=", ".join(_commands(server)), origin=_origin(server))
    for extra in _extras(server):
        detail = said("{text}; {more}", text=detail, more=extra)
    title = said("Runs here: {name}", name=server.name)
    if server.source == EXTRAS:
        return SetupCheck(f"mcp:{server.name}", title, "ok", detail)
    status = "warn" if server.trusted or not server.source else "ok"
    return SetupCheck(f"mcp:{server.name}", title, status, detail, _PLUGIN_FIX if status == "warn" else "")


def _commands(server: McpServer) -> list[str]:
    found = [server.command, server.page_command, server.channel_command, server.agent_worker]
    return list(dict.fromkeys(c.rsplit("/", 1)[-1] for c in found if c))


def _origin(server: McpServer) -> str:
    if server.source == EXTRAS:
        return said("from the official extras")
    if server.source:
        return said("from {source}, not official", source=server.source)
    return said("added by hand")


def _extras(server: McpServer) -> list[str]:
    given = [
        (server.trusted, said("trusted: its tools run without asking")),
        (server.ssh_agent, said("gets your ssh agent")),
        (bool(server.model_login), said("gets the model's login")),
        (server.login_session, said("opens apps on your screen")),
    ]
    return [text for on, text in given if on]
