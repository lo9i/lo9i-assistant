"""What a plugin is for, to group plugins in the apps: a group and a category in it, written as a path
(`communications/email`). In a repository, plugins live in their category's folder
(`communications/email/gmail`, `apps/finance/expenses`), which gives their category; a plugin
elsewhere (a repository that is one plugin) declares it with `category:` in its server.yaml or
SKILL.md. The list is fixed, so repositories can't spread over near-duplicates. What a plugin does
still comes from the sections of its server.yaml; the category only groups it."""

from pathlib import Path, PurePosixPath

from assistant.core.i18n import said
from assistant.core.repositories.folders import subfolders

CATEGORIES = (
    "apps/finance",
    "apps/media",
    "assistant/agents",
    "assistant/modes",
    "communications/chat",
    "communications/contacts",
    "communications/email",
    "communications/phone",
    "connectivity/remote",
    "media/news",
    "media/video",
    "other/general",
    "productivity/calendar",
    "productivity/documents",
    "productivity/maps",
    "software/factory",
)
DEFAULT = "other/general"
# The category a plugin with that section of server.yaml is in.
_SECTIONS = {"channel": "communications/chat", "email": "communications/email"}


def plugin_folders(root: Path) -> list[Path]:
    """The folders in the repository's category folders: one plugin each."""
    return [folder for category in CATEGORIES for folder in subfolders(root / category)]


def of_folder(root: Path, folder: Path) -> str:
    """The category whose folder holds this plugin's folder, or "" outside them."""
    try:
        return of_path(folder.relative_to(root).as_posix())
    except ValueError:
        return ""


def of_path(path: str) -> str:
    """The category whose folder holds the plugin at this path in its repository, or "" outside them."""
    parent = str(PurePosixPath(path).parent)
    return parent if parent in CATEGORIES else ""


def parse(value: object, sections: set[str], folder: str = "") -> str:
    """The plugin's category: its folder's, else the one it declares, else its sections', else the
    default. Raises ValueError for one that isn't in the list, that disagrees with its folder, or that
    its sections don't allow."""
    declared = str(value or "")
    if folder and declared and declared != folder:
        raise ValueError(
            said("it's in the {folder} folder, but its category says {declared}", folder=folder, declared=declared)
        )
    needed = sorted({_SECTIONS[s] for s in sections if s in _SECTIONS})
    category = folder or declared or (needed[0] if needed else DEFAULT)
    if category not in CATEGORIES:
        raise ValueError(
            said(
                "its category {category!r} isn't one of {categories}",
                category=category,
                categories=", ".join(CATEGORIES),
            )
        )
    if needed and category not in needed:
        raise ValueError(
            said(
                "it's a {sections} plugin, so its category must be {category}",
                sections=" and ".join(sorted(sections)),
                category=needed[0],
            )
        )
    return category
