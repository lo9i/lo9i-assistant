"""Connected clients as a Markdown table, shared by the /sessions screen and the plain REPL."""

from assistant.protocol import ConnectedClient


def describe(clients: list[ConnectedClient], own_id: str) -> str:
    if not clients:
        return "## Connected clients\n\nNone."
    header = "| Client | Connection | Connected since |\n|---|---|---|"
    rows = [f"| {_name(c, own_id)} | {c.transport} | {_when(c.connected_at)} |" for c in clients]
    return "## Connected clients\n\n" + "\n".join([header, *rows])


def _name(client: ConnectedClient, own_id: str) -> str:
    kind = client.kind or "unknown"
    return f"{kind} (this one)" if own_id and client.id == own_id else kind


def _when(timestamp: str) -> str:
    return f"{timestamp[:19].replace('T', ' ')} UTC"
