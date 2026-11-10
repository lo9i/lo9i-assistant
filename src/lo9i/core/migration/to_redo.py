"""What an import can't bring along, said to the user once it's staged: what's set up per computer, outside lo9i's data
home, or tied to the old computer. Read from the export's manifest and the plugins it brings (their server.yaml)."""

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lo9i.core.i18n import said
from lo9i.core.migration import home as contents
from lo9i.core.migration.manifest import Manifest
from lo9i.core.repositories import platforms
from lo9i.core.repositories.folders import SERVER_FILE


@dataclass(frozen=True)
class _Plugin:
    name: str
    platforms: list[str] = field(default_factory=list)
    channel: bool = False
    agent_command: str = ""
    ssh_agent: bool = False


def to_redo(manifest: Manifest, brought: Path, user_home: Path) -> list[str]:
    """`brought`: the export's home, unpacked. Each item one sentence or two, in the order to do them."""
    plugins = _plugins(brought / contents.CODE)
    items = [
        said("Stop lo9i on the old computer ({host}), so chat channels and jobs run in one place.", host=manifest.host),
        said("Turn on Start at boot again (Settings → General): it's set up on each computer."),
        said(
            "The checkout's .env isn't in the export: a model key or HTTPS settings kept there go in this computer's "
            ".env."
        ),
        said(
            "Browsers paired with the old computer stay paired only if they reach this one at the same address; pair "
            "the others again, and add their passkeys again."
        ),
        *_plugin_items(plugins, manifest),
        *_path_items(manifest, user_home, plugins),
        said("The speech and memory search models are downloaded again the first time they're used."),
    ]
    return items


def _plugin_items(plugins: list[_Plugin], manifest: Manifest) -> list[str]:
    items = []
    if elsewhere := [p.name for p in plugins if not platforms.runs_here(p.platforms)]:
        items.append(
            said(
                "{names} don't run on {system}: remove them in Plugins.",
                names=", ".join(elsewhere),
                system=platforms.current(),
            )
        )
    if channels := [p.name for p in plugins if p.channel]:
        items.append(
            said(
                "Chat channels ({names}) keep their sign-in; one the service ends on a new computer (a linked "
                "device) is set up again from its details in Plugins.",
                names=", ".join(channels),
            )
        )
    if keys := [p.name for p in plugins if p.ssh_agent]:
        items.append(
            said("{names} use your ssh keys, which aren't in the export: add them here.", names=", ".join(keys))
        )
    if not manifest.same_system():
        items.append(
            said(
                "The export comes from {system}: websites plugins signed in to in their browser may ask to sign in "
                "again, and the browser that renders pages is downloaded again.",
                system=manifest.system,
            )
        )
    return items


def _path_items(manifest: Manifest, user_home: Path, plugins: list[_Plugin]) -> list[str]:
    items = []
    if manifest.user_home != str(user_home):
        items.append(
            said("Paths under {old} now point to {new}.", old=manifest.user_home, new=str(user_home)),
        )
    for plugin in (p for p in plugins if p.agent_command):
        items.append(_agent_item(plugin.agent_command))
    return items


def _agent_item(command: str) -> str:
    if shutil.which(command) is None:
        return said(
            "Coding agents' sessions stay on the old computer, and the projects handed to them need copying to the "
            "same place under your home folder. {command} isn't installed here yet: install it and sign in.",
            command=command,
        )
    return said(
        "Coding agents' sessions stay on the old computer, and the projects handed to them need copying to the same "
        "place under your home folder. {command} is installed here: check it's signed in.",
        command=command,
    )


def _plugins(code: Path) -> list[_Plugin]:
    found = []
    for manifest in sorted(code.glob(f"*/{SERVER_FILE}")) if code.is_dir() else []:
        try:
            data: Any = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            found.append(_plugin(manifest.parent.name, data))
        except (OSError, yaml.YAMLError, TypeError, ValueError, AttributeError):
            # Only this list leaves it out: the plugin itself says what's wrong with it once the daemon reads it.
            continue
    return found


def _plugin(name: str, data: dict[str, Any]) -> _Plugin:
    agent = data.get("agent") or {}
    return _Plugin(
        name,
        platforms.parse(data.get("platforms")),
        channel=bool(data.get("channel")),
        agent_command=str(agent.get("command", "")) if isinstance(agent, dict) else "",
        ssh_agent=bool(data.get("ssh_agent")),
    )
