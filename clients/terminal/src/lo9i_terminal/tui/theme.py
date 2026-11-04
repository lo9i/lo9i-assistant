"""The app's own colors, the same in every terminal (whatever its palette: a green-on-black profile made all the text
green): light text on a dark ground, gray structure, the brand's teal-gray behind what's picked, and color kept for
meaning: the user's words, warnings and errors. app.tcss names the same colors as variables; keep them in step."""

from textual.theme import Theme

NAME = "lo9i"

GROUND = "#1e2425"
TEXT = "#d9dfdf"
MUTED = "#8c999a"
LINE = "#4b5657"
BRAND = "#364445"
ACCENT = "#8fc4cf"
_PANEL = "#283031"

THEME = Theme(
    name=NAME,
    primary=ACCENT,
    secondary=ACCENT,
    accent=ACCENT,
    warning="#e3bd6b",
    error="#e8806f",
    success="#9ccfae",
    foreground=TEXT,
    background=GROUND,
    surface=GROUND,
    panel=_PANEL,
    dark=True,
    variables={
        "border": MUTED,
        "border-blurred": LINE,
        # What's picked in a list: the brand's teal-gray, the text kept readable on it, whether the list has focus
        # (brighter) or not.
        "block-cursor-background": BRAND,
        "block-cursor-foreground": "#f1f4f4",
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-background": "#2c3738",
        "block-cursor-blurred-foreground": TEXT,
        "block-cursor-blurred-text-style": "none",
        "block-hover-background": "#2a3334",
        "input-cursor-background": TEXT,
        "input-cursor-foreground": GROUND,
        "input-selection-background": BRAND,
        "screen-selection-background": BRAND,
        "footer-background": GROUND,
        "footer-key-foreground": ACCENT,
        "footer-description-foreground": MUTED,
        "markdown-h1-color": TEXT,
        "markdown-h1-background": "transparent",
        "markdown-h1-text-style": "bold",
        "markdown-h2-color": TEXT,
        "markdown-h2-background": "transparent",
        "markdown-h2-text-style": "bold",
        "markdown-h3-color": TEXT,
        "markdown-h3-background": "transparent",
        "markdown-h3-text-style": "bold",
        "link-color": ACCENT,
        "link-background": "transparent",
        "link-style": "underline",
        "link-color-hover": TEXT,
        "link-background-hover": "transparent",
        "scrollbar": LINE,
        "scrollbar-hover": MUTED,
        "scrollbar-active": MUTED,
        "scrollbar-background": GROUND,
        "scrollbar-background-hover": GROUND,
        "scrollbar-background-active": GROUND,
        "scrollbar-corner-color": GROUND,
    },
)
