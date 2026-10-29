"""Connected clients as a Markdown table, shared by the /sessions screen and the plain REPL."""

from assistant.protocol import ConnectedClient
from assistant_terminal.i18n import t


def describe(clients: list[ConnectedClient], own_id: str) -> str:
    title = "## " + t("Connected clients")
    if not clients:
        return f"{title}\n\n" + t("None.")
    header = f"| {t('Client')} | {t('Connection')} | {t('Connected since')} |\n|---|---|---|"
    rows = [f"| {_name(c, own_id)} | {c.transport} | {_when(c.connected_at)} |" for c in clients]
    return f"{title}\n\n" + "\n".join([header, *rows])


def _name(client: ConnectedClient, own_id: str) -> str:
    kind = client.kind or t("unknown")
    return t("{kind} (this one)", kind=kind) if own_id and client.id == own_id else kind


def _when(timestamp: str) -> str:
    return f"{timestamp[:19].replace('T', ' ')} UTC"
