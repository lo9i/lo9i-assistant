"""An MCP server for the tests that goes on working after its tool returns, following
docs/background-work.md: `start_work` says the work started, and a moment later that it finished,
with the call's origin."""

import asyncio

from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context

server = MCPServer("background")
_running: set[asyncio.Task] = set()


@server.tool()
async def start_work(name: str, ctx: Context) -> str:
    """Start some work that goes on after this returns."""
    request = ctx.request_context
    origin = (request.meta or {}).get("lo9i/origin")
    # The connection's own channel, not the request's, which closes when the call returns.
    connection = request.session._connection.outbound
    await connection.notify("notifications/lo9i/work_started", {"work": name})
    task = asyncio.get_running_loop().create_task(_finish(connection, name, origin))
    _running.add(task)
    return f"Started {name}."


async def _finish(connection, name: str, origin: dict | None) -> None:
    await asyncio.sleep(0.3)
    params = {"work": name, "origin": origin, "ok": True, "text": f"{name} is ready: 3 files converted."}
    await connection.notify("notifications/lo9i/work_finished", params)


if __name__ == "__main__":
    server.run()
