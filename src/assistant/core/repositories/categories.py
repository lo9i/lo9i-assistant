"""What a plugin is for, to group plugins in the apps: `category:` in its server.yaml or SKILL.md. The
list is fixed, so the extras can't spread over near-duplicates. What a plugin does still comes from the
sections of its server.yaml; the category only groups it."""

CATEGORIES = ("communications", "finance", "other")
DEFAULT = "other"
# The category a plugin with that section of server.yaml is in.
_SECTIONS = {"channel": "communications", "email": "communications"}


def parse(value: object, sections: set[str]) -> str:
    """The category a plugin declares, checked against the sections it has. Without one, a plugin is
    in its sections' category, or `other`. Raises ValueError for a category that isn't in the list or
    that its sections don't allow."""
    needed = sorted({_SECTIONS[s] for s in sections if s in _SECTIONS})
    category = str(value or (needed[0] if needed else DEFAULT))
    if category not in CATEGORIES:
        raise ValueError(f"its category {category!r} isn't one of {', '.join(CATEGORIES)}")
    if needed and category not in needed:
        raise ValueError(f"it's a {' and '.join(sorted(sections))} plugin, so its category must be {needed[0]}")
    return category
