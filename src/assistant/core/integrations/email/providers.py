"""Mail providers to pick from when connecting email, so the user types only their address and a
password, or signs in (OAuth: Google, Microsoft). Each comes from an email plugin, which declares its
presets in the `email:` section of its server.yaml (core/mcp/install.py) and runs nothing. A `custom`
preset has no servers: the user enters them (the extras' custom-email plugin). A preset's name and help come in
other languages from the plugin's `translations:` (`in_language`)."""

from dataclasses import dataclass, field, replace
from typing import Any

from assistant.core.i18n import said

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
    # How to get the password this provider wants, in Markdown (a numbered list of steps, links), and where.
    password_help: str = ""
    password_url: str = ""
    # False while the provider can't connect; `password_help` says why.
    supported: bool = True
    # Signs in with OAuth instead of a password: "google" or "microsoft" (oauth.py). Then
    # `password_help` explains registering the OAuth app, and `password_url` is where.
    oauth: str = ""
    # The plugin that offers it; its accounts belong to that plugin.
    plugin: str = ""
    # The user enters the servers (SMTP host and port, IMAP host), so it declares none.
    custom: bool = False
    # Its name and help in the apps' other languages, by language (`translations:` in its plugin's server.yaml).
    translations: dict[str, dict[str, str]] = field(default_factory=dict)


def in_language(provider: EmailProvider, language: str) -> EmailProvider:
    """With its name and help as its plugin translates them to `language`, English where it doesn't."""
    texts = provider.translations.get(language, {})
    return replace(
        provider,
        name=texts.get("name") or provider.name,
        password_help=texts.get("password_help") or provider.password_help,
    )


def parse(section: object, plugin: str, translations: dict[str, dict[str, dict[str, str]]]) -> list[EmailProvider]:
    """The presets in a plugin's `email:` section, with their texts in `translations` (by language, then by
    provider id). Raises ValueError for one that can't be used."""
    if section is None:
        return []
    if not isinstance(section, list) or not all(isinstance(e, dict) for e in section):
        raise ValueError(said("its email: section must be a list of providers"))
    found = [_provider(entry, plugin) for entry in section]
    ids = {p.id for p in found}
    if len(ids) != len(found):
        raise ValueError(said("its email: section has two providers with the same id"))
    if unknown := sorted({i for texts in translations.values() for i in texts} - ids):
        raise ValueError(said("its translations name email providers it doesn't have: {ids}", ids=", ".join(unknown)))
    return [replace(p, translations=_texts_of(p.id, translations)) for p in found]


def translated(value: object) -> dict[str, dict[str, str]]:
    """A language's `email:` section in `translations:`: each provider's name and help by its id. Raises
    ValueError for one that can't be used."""
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(texts, dict) for texts in value.values()):
        raise ValueError(said("its translations' email must be a section per provider id"))
    return {
        str(i): {k: str(texts.get(k) or "").strip() for k in ("name", "password_help")} for i, texts in value.items()
    }


def _texts_of(provider: str, translations: dict[str, dict[str, dict[str, str]]]) -> dict[str, dict[str, str]]:
    return {language: texts[provider] for language, texts in translations.items() if provider in texts}


def _provider(entry: dict[str, Any], plugin: str) -> EmailProvider:
    custom = bool(entry.get("custom", False))
    required = ("id", "name") if custom else _REQUIRED
    if missing := [key for key in required if not str(entry.get(key) or "").strip()]:
        raise ValueError(said("a provider in its email: section has no {missing}", missing=", ".join(missing)))
    if (oauth := str(entry.get("oauth") or "")) not in _OAUTH:
        raise ValueError(
            said(
                "its email: provider {provider} signs in with {oauth!r}, not google or microsoft",
                provider=entry["id"],
                oauth=oauth,
            )
        )
    return EmailProvider(
        str(entry["id"]),
        str(entry["name"]),
        str(entry.get("host") or ""),
        int(entry.get("port", 587)),
        str(entry.get("imap_host") or ""),
        str(entry.get("password_help") or "").strip(),
        str(entry.get("password_url") or ""),
        bool(entry.get("supported", True)),
        oauth,
        plugin,
        custom,
    )
