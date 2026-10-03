"""Slack setup text (Markdown), shared by the setup screen and the plain REPL."""

from assistant.core.agent import SlackStatus

STEPS = """## Connect Slack

1. Open https://api.slack.com/apps, choose **Create New App → From a manifest**, and pick your workspace.
2. Paste the app manifest, then choose **Next → Create**.
3. In **Basic Information → App-Level Tokens**, choose **Generate Token and Scopes**, add the scope
   `connections:write`, and generate. Copy the token that starts with `xapp-`.
4. In **OAuth & Permissions**, choose **Install to** your workspace, then **Allow**. The same page then
   shows the **Bot User OAuth Token** (`xoxb-`) and the **User OAuth Token** (`xoxp-`)."""


def describe(status: SlackStatus, error: str) -> str:
    if not status.connected:
        return STEPS + (f"\n\n**{error}**" if error else "")
    return "\n\n".join(
        [
            f"**Slack: {status.team}**",
            _state(status),
            f"Only {status.owner_name} can talk to the assistant. In Slack, open the app under **Apps** in "
            "the sidebar and send it a message. `/new` starts a new conversation.",
        ]
    )


def _state(status: SlackStatus) -> str:
    if status.running:
        return "Connection: open ✓"
    return "Connection: **not open**. The daemon connects within a few seconds; if it doesn't, see `daemon.log`."
