"""When a plugin's page is of use (`shown:` in its server.yaml's `page:` section): `always`, or only `without_screen`,
on a computer with no screen to show windows on, where the page stands in for one (the browser plugin's live view on
a Linux server). A page not of use here isn't run, listed in the web app's sidebar or offered by Home's sections.

A computer has a screen unless it's Linux with neither DISPLAY nor WAYLAND_DISPLAY in the daemon's environment, which
its plugins' processes get too, so a plugin that reads them decides the same way."""

import os
import sys
from typing import Literal, cast, get_args

from lo9i.core.i18n import said
from lo9i.core.mcp.servers import McpServer

Shown = Literal["always", "without_screen"]


def parse(value: object) -> Shown:
    """Raises ValueError for a value it doesn't know."""
    if value is None:
        return "always"
    if value not in get_args(Shown):
        raise ValueError(said("its page's shown must be always or without_screen"))
    return cast(Shown, value)


def of_use(server: McpServer) -> bool:
    """Whether the server has a page and it's of use on this computer."""
    return bool(server.page_command) and (server.page_shown == "always" or not has_screen())


def has_screen() -> bool:
    return sys.platform != "linux" or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
