"""Chat channels (Telegram, Slack, WhatsApp: plugins) as text, for /plugins and the plain REPL. Each
channel says what to show for setting it up (its items); nothing here knows a particular channel."""

import segno

from assistant.core.agent import ChannelStatus, SetupItem

# Two rows of modules in each line of text: (top dark, bottom dark) → the character drawn dark on light.
_HALVES = {(True, True): "█", (True, False): "▀", (False, True): "▄", (False, False): " "}
# The light border scanners need around a QR code, in modules.
_QUIET = 2


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


def qr_lines(value: str) -> list[str]:
    """A QR item's code in half blocks, to draw dark on light: a terminal's characters are about twice as tall as
    wide, so each holds two modules, one above the other, and the code comes out square."""
    rows = [[bool(module) for module in row] for row in segno.make_qr(value).matrix_iter(border=_QUIET)]
    if len(rows) % 2:
        rows.append([False] * len(rows[0]))
    pairs = [(rows[y], rows[y + 1]) for y in range(0, len(rows), 2)]
    return ["".join(_HALVES[pair] for pair in zip(top, bottom, strict=True)) for top, bottom in pairs]


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
    if item.kind == "qr":
        # The REPL's colours follow the terminal's, and a QR code drawn light on dark doesn't scan.
        named = f": {item.label}" if item.label else ""
        return f"QR code{named} (scan it in the full-screen app, in /plugins)"
    return line(item)
