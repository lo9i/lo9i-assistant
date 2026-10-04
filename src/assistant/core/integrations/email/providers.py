"""Mail providers to pick from when connecting email, so the user types only their address and a
password, or signs in (OAuth: Google, Microsoft). Each comes from an email plugin, which declares its
presets in the `email:` section of its server.yaml (core/mcp/install.py) and runs nothing. Clients
offer "Other" for entering the servers by hand, which needs no plugin."""

from dataclasses import dataclass
from typing import Any

_OAUTH = {"", "google", "microsoft"}
_REQUIRED = ("id", "name", "host", "imap_host")


@dataclass(frozen=True)
class EmailProvider:
    # Unique within its plugin.
    id: str
    name: str
    host: str
    port: int
    # IMAP over TLS (port 993), for reading mail.
    imap_host: str
    # How to get the password this provider wants, and where.
    password_help: str = ""
    password_url: str = ""
    # False while the provider can't connect; `password_help` says why.
    supported: bool = True
    # Signs in with OAuth instead of a password: "google" or "microsoft" (oauth.py). Then
    # `password_help` explains registering the OAuth app, and `password_url` is where.
    oauth: str = ""
    # The plugin that offers it; its accounts belong to that plugin.
    plugin: str = ""


def parse(section: object, plugin: str) -> list[EmailProvider]:
    """The presets in a plugin's `email:` section. Raises ValueError for one that can't be used."""
    if section is None:
        return []
    if not isinstance(section, list) or not all(isinstance(e, dict) for e in section):
        raise ValueError("its email: section must be a list of providers")
    found = [_provider(entry, plugin) for entry in section]
    if len({p.id for p in found}) != len(found):
        raise ValueError("its email: section has two providers with the same id")
    return found


def _provider(entry: dict[str, Any], plugin: str) -> EmailProvider:
    if missing := [key for key in _REQUIRED if not str(entry.get(key) or "").strip()]:
        raise ValueError(f"a provider in its email: section has no {', '.join(missing)}")
    if (oauth := str(entry.get("oauth") or "")) not in _OAUTH:
        raise ValueError(f"its email: provider {entry['id']} signs in with {oauth!r}, not google or microsoft")
    return EmailProvider(
        str(entry["id"]),
        str(entry["name"]),
        str(entry["host"]),
        int(entry.get("port", 587)),
        str(entry["imap_host"]),
        str(entry.get("password_help") or "").strip(),
        str(entry.get("password_url") or ""),
        bool(entry.get("supported", True)),
        oauth,
        plugin,
    )
