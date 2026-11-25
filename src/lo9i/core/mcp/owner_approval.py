"""The owner's approval before a paired device has this computer run code.

A device paired over the network could otherwise run whatever it likes as the user: a local MCP server's command, an
environment variable that makes that command load other code, a plugin installed from a repository. Its token could be
stolen, so such a request waits for the owner's answer on a chat channel they carry (core/approvals.py, the
`ja:`/`jr:` buttons a scheduled job's approval gets). With no channel connected, or no answer in time, it's refused.
The Unix socket (the terminal app on this computer) is the owner and isn't asked.
"""

import fnmatch
import shlex
import uuid
from collections.abc import Mapping

from lo9i.core.approvals import RemoteApprovals
from lo9i.core.i18n import said
from lo9i.core.mcp.servers import McpServer, McpServerError
from lo9i.core.skills.store import Skill

# Environment variables that make a process load or run code other than its command: where programs and libraries
# are looked up, code an interpreter runs or loads at start, the dynamic linker's preloads. Globs.
CODE_VARIABLES = (
    "PATH",
    "LD_*",
    "DYLD_*",
    "PYTHON*",
    "NODE_OPTIONS",
    "NODE_PATH",
    "PERL5LIB",
    "PERL5OPT",
    "PERLLIB",
    "RUBYOPT",
    "RUBYLIB",
    "GEM_HOME",
    "GEM_PATH",
    "JAVA_TOOL_OPTIONS",
    "_JAVA_OPTIONS",
    "JDK_JAVA_OPTIONS",
    "CLASSPATH",
    "BASH_ENV",
    "ENV",
    "SHELLOPTS",
    "PS4",
    "PROMPT_COMMAND",
    "ZDOTDIR",
    "HOME",
    "XDG_CONFIG_HOME",
    "UV_*",
    "VIRTUAL_ENV",
    "NPM_CONFIG_*",
    "GIT_*",
    "LUA_PATH",
    "LUA_CPATH",
    "TCLLIBPATH",
)

Request = dict[str, str]


class NotApprovedError(McpServerError):
    """The owner didn't approve the code a device asked to run: they rejected it, nobody answered, or no chat channel
    could ask them."""


async def ask(approvals: RemoteApprovals, request: Request, device: str, minutes: int) -> None:
    """Returns once the owner approved `request`. Raises NotApprovedError otherwise."""
    if not approvals.available:
        raise NotApprovedError(
            said(
                "This runs code on the computer lo9i runs on, so doing it from another device needs your approval on "
                "a connected chat channel, and none is connected. Connect one, or do it from the app on that computer."
            )
        )
    decision = await approvals.ask(uuid.uuid4().hex, f"The device {device}", request, minutes * 60)
    if decision is None:
        raise NotApprovedError(said("Nobody approved it within {minutes} minutes.", minutes=minutes))
    if not decision.get("approved"):
        raise NotApprovedError(said("It was rejected."))


def runs_code(server: McpServer) -> bool:
    """Anything of the server's that runs on this computer: its MCP server, page, channel, agent worker or check."""
    commands = (server.command, server.page_command, server.channel_command, server.agent_worker, server.check_command)
    return any(c.strip() for c in commands)


def runs_code_variables(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """The variables among CODE_VARIABLES the change gives, changes or takes away, in order."""
    touched = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    return sorted(k for k in touched if any(fnmatch.fnmatchcase(k, p) for p in CODE_VARIABLES))


def local_server(server: McpServer, device: str) -> Request:
    """For a local server's command, with the variables of its env that change what it runs."""
    risky = {k: v for k, v in server.env.items() if k in runs_code_variables({}, server.env)}
    return _request(f"the local MCP server {server.name}", device, _command(server, risky))


def code_variables(server: McpServer, names: list[str], device: str) -> Request:
    """For variables of a local server's env that change what its command runs."""
    given = {n: server.env[n] for n in names if n in server.env}
    gone = "".join(f"\nunset {n}" for n in names if n not in server.env)
    return _request(f"environment variables of the MCP server {server.name}", device, _command(server, given) + gone)


def repository_install(url: str, plugins: list[McpServer], skills: list[Skill], device: str) -> Request:
    """For plugins and skills with scripts installed from a repository, each with what it runs."""
    lines = [
        f"{s.name}: {shlex.join([s.command, *s.args]) if s.command else 'runs its own processes'}" for s in plugins
    ]
    lines += [f"{s.name}: a skill with {', '.join(s.files)}" for s in skills]
    return _request(f"plugins from {url}", device, "\n".join(lines))


def repository(url: str, device: str) -> Request:
    """For a repository added to install plugins from."""
    return _request(f"the plugin repository {url}", device, url)


def _command(server: McpServer, env: Mapping[str, str]) -> str:
    assignments = [f"{k}={v}" for k, v in env.items()]
    return shlex.join([*assignments, server.command, *server.args])


def _request(what: str, device: str, details: str) -> Request:
    """As a tool's approval reads in a chat (core/channels/chat/approvals.py): what, why, and the details."""
    reason = f"the device {device} wants this to run code on this computer"
    return {"tool": what, "reason": reason, "command": details}
