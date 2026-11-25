"""The owner's approval before a paired device runs a command on this computer as an MCP server.

A device paired over the network can add, probe or change a server's command. Its token could be stolen, and a
local server is code run as the user, so the request waits for the owner's answer on a chat channel they carry
(core/approvals.py, the `ja:`/`jr:` buttons a scheduled job's approval gets). With no channel connected, or no answer
in time, it's refused. The Unix socket (the terminal app on this computer) is the owner and isn't asked.
"""

import shlex
import uuid

from lo9i.core.approvals import RemoteApprovals
from lo9i.core.i18n import said
from lo9i.core.mcp.servers import McpServer, McpServerError


class NotApprovedError(McpServerError):
    """The owner didn't approve running the server's command: they rejected it, nobody answered, or no chat channel
    could ask them."""


async def ask_owner(approvals: RemoteApprovals, server: McpServer, device: str, minutes: int) -> None:
    """Returns once the owner approved the server's command. Raises NotApprovedError otherwise."""
    if not approvals.available:
        raise NotApprovedError(
            said(
                "A local MCP server runs a command on the computer lo9i runs on, so adding it from another device "
                "needs your approval on a connected chat channel, and none is connected. Connect one, or add it from "
                "the app on that computer."
            )
        )
    decision = await approvals.ask(uuid.uuid4().hex, f"The device {device}", _request(server, device), minutes * 60)
    if decision is None:
        raise NotApprovedError(said("Nobody approved running this command within {minutes} minutes.", minutes=minutes))
    if not decision.get("approved"):
        raise NotApprovedError(said("Running this command as an MCP server was rejected."))


def _request(server: McpServer, device: str) -> dict[str, str]:
    """As a tool's approval reads in a chat (core/channels/chat/approvals.py): what, why, and the command itself."""
    return {
        "tool": f"the local MCP server {server.name}",
        "reason": f"the device {device} wants to run this command on this computer",
        "command": shlex.join([server.command, *server.args]),
    }
