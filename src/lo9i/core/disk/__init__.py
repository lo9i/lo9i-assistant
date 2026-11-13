"""The disk lo9i takes: how much, by category (its database, the models it downloaded, plugins' code and data, the
browser page rendering uses, uploads, logs, workspaces, old copies of its data, the files plugins download elsewhere),
and cleaning what can go without losing anything: old logs, old copies of its data, uploads nothing refers to,
caches in plugins' folders, the database's free space, and the plugins' downloads only when the user names them.
Never the models, a browser's profile or the database itself."""

from lo9i.core.disk.cleaning import Cleaned, CleanFailure, clean
from lo9i.core.disk.places import CATEGORIES, Places, from_settings
from lo9i.core.disk.report import ON_REQUEST, CleanItem, DiskCategory, DiskReport, build

__all__ = [
    "CATEGORIES",
    "ON_REQUEST",
    "CleanFailure",
    "CleanItem",
    "Cleaned",
    "DiskCategory",
    "DiskReport",
    "Places",
    "build",
    "clean",
    "from_settings",
]
