"""A mostly monochrome theme on the terminal's own colors. Structure is gray, emphasis is bold,
and color is kept for meaning only: green for the user, yellow for warnings, red for errors."""

from dataclasses import replace

from textual.theme import BUILTIN_THEMES, Theme

NAME = "lo9i"

_GRAY = "ansi_bright_black"

THEME: Theme = replace(
    BUILTIN_THEMES["ansi-dark"],
    name=NAME,
    primary=_GRAY,
    secondary=_GRAY,
    accent="ansi_default",
    variables={
        **BUILTIN_THEMES["ansi-dark"].variables,
        "border": _GRAY,
        "border-blurred": _GRAY,
        "markdown-h1-color": "ansi_default",
        "markdown-h1-background": "ansi_default",
        "markdown-h1-text-style": "bold",
        "markdown-h2-color": "ansi_default",
        "markdown-h2-background": "ansi_default",
        "markdown-h2-text-style": "bold",
        "markdown-h3-color": "ansi_default",
        "markdown-h3-background": "ansi_default",
        "markdown-h3-text-style": "bold",
        "link-color": "ansi_default",
        "link-background": "ansi_default",
        "link-style": "underline",
        "link-color-hover": "ansi_default",
        "link-background-hover": "ansi_default",
        "footer-key-foreground": "ansi_default",
        "input-selection-background": _GRAY,
        "screen-selection-background": _GRAY,
    },
)
