"""Chat channels (Telegram, Slack: plugins) as text, for /plugins and the plain REPL. Each
channel says what to show for setting it up (its items); nothing here knows a particular channel."""

from assistant.core.agent import ChannelStatus, SetupItem


def state(channel: ChannelStatus) -> str:
    if not channel.enabled:
        return "off"
    return "connected ✓" if channel.connected else "not connected"


def title(name: str) -> str:
    """A channel's name as a title: "telegram" → "Telegram"."""
    return name[:1].upper() + name[1:]


def heading(channel: ChannelStatus) -> str:
    return f"{title(channel.name)} · {state(channel)}"


def line(item: SetupItem) -> str:
    """A text or code item as one line: "label: value", or the value alone."""
    return f"{item.label}: {item.value}" if item.label else item.value


def describe(channel: ChannelStatus) -> str:
    """Markdown for the plain REPL, which can't press buttons."""
    parts = [f"**{heading(channel)}**", *[_markdown(item) for item in channel.items]]
    return "\n\n".join(parts)


def _markdown(item: SetupItem) -> str:
    if item.kind == "code":
        return f"{item.label}: **`{item.value}`**" if item.label else f"**`{item.value}`**"
    if item.kind == "copy":
        return f"{item.label}:\n\n```\n{item.value}\n```"
    if item.kind == "action":
        return f"Button: {item.label} (press it in the full-screen app, in /plugins)"
    return line(item)
