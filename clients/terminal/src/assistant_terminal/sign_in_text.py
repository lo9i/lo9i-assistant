"""Signing in (OAuth) from the terminal app: the browser is sent back to the daemon's web app on this
computer, which finishes it, or the user pastes the address the browser ended on."""

from urllib.parse import parse_qs, urlparse

from assistant.core.config import settings

# The daemon's web app on this computer: providers allow http for localhost.
REDIRECT = f"http://localhost:{settings.daemon_port}/app/oauth"
PASTE_HINT = "Paste the address your browser ended on, if it didn't finish by itself"
MISSING_CODE = "**Paste the whole address your browser ended on: it has `code=` and `state=` in it.**"


def signing_message(url: str, opened: bool, shows_up: str) -> str:
    browser = "A browser opened with it" if opened else "Open it in a browser"
    return (
        f"{browser}: [sign in]({url})\n\nOn this computer, the browser comes back to the assistant and "
        f"{shows_up}. Elsewhere (over SSH), paste the address the browser ended on, then Finish."
    )


def returned(address: str) -> tuple[str, str]:
    """The state and code in the address the provider sent the browser back to."""
    query = parse_qs(urlparse(address.strip()).query)
    return query.get("state", [""])[0], query.get("code", [""])[0]
