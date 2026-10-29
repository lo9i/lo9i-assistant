"""Web search setup text (Markdown), shared by the setup screen and the plain REPL."""

from assistant.core.agent import WebSearchStatus
from assistant_terminal.i18n import t


def describe(status: WebSearchStatus, error: str) -> str:
    text = _key_set() if status.brave_key_set else _no_key()
    return f"{text}\n\n**{error}**" if error else text


def _no_key() -> str:
    return "\n\n".join(
        [
            "## " + t("Web search"),
            t(
                "Searches use public engines and free search services (Exa, Parallel, Keenable), which can block or "
                "limit automated searches. A Brave Search API key makes search reliable:"
            ),
            "\n".join(
                [
                    "1. " + t("Open https://brave.com/search/api/ and sign up for the free plan."),
                    "2. " + t("In the dashboard, open **API Keys** and copy the key."),
                    "3. "
                    + t("Paste it below.")
                    + " "
                    + t("It's checked with one search, then kept encrypted on the assistant's computer."),
                ]
            ),
        ]
    )


def _key_set() -> str:
    return (
        "## "
        + t("Web search")
        + "\n\n"
        + t("Searches use the Brave Search API. When Brave fails, they use public engines and free search services.")
    )
