"""User-managed domain blocklist (`WEB_BLOCKED_DOMAINS`). A blocked domain also blocks its subdomains."""

from urllib.parse import urlsplit

from assistant.core.config import settings


class BlockedDomainError(Exception):
    pass


def check_allowed(url: str) -> None:
    host = (urlsplit(url).hostname or "").lower()
    for domain in settings.web_blocked_domains:
        domain = domain.lower().lstrip(".")
        if host == domain or host.endswith("." + domain):
            raise BlockedDomainError(f"{host} is on the blocked domain list")
