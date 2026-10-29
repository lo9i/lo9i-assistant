"""A plugin's icon, which the web app shows beside it (the sidebar's pages, Plugins, Home, notifications):
`icon:` in its server.yaml or SKILL.md, either the name of a Lucide icon, the set the web app draws with
(`tv`, as on lucide.dev), or an SVG file in the plugin's folder (`icon: icon.svg`). Without one, its
category's icon (CATEGORY_ICONS).

An SVG is kept as its text and shown only as an image or a mask (data URLs, which the web app's policy
allows for images), where a browser runs nothing in it; it's checked here too, so a plugin with one that
could do more is a problem of the repository's, as an invalid SKILL.md is. One that draws only in
`currentColor` is `mono`: the web app paints it in the theme's text colour, like its own icons; any other
keeps its colours (a brand's logo).

The Lucide names are the icons of the web app's Lucide (lucide_icons.json), which a test there keeps in
step with the version it has."""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import cache
from pathlib import Path

# Big enough for a detailed logo; an icon has no use for more.
MAX_SVG_BYTES = 32 * 1024
CATEGORY_ICONS = {
    "apps/finance": "wallet",
    "apps/media": "clapperboard",
    "assistant/agents": "bot",
    "assistant/modes": "sliders-horizontal",
    "communications/chat": "message-circle",
    "communications/contacts": "contact",
    "communications/email": "mail",
    "communications/phone": "phone",
    "connectivity/remote": "server",
    "media/news": "newspaper",
    "media/video": "video",
    "other/general": "puzzle",
    "productivity/calendar": "calendar",
    "productivity/maps": "map",
    "software/factory": "factory",
}
_SVG_NS = "{http://www.w3.org/2000/svg}"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
# Drawing only: nothing that runs, loads or embeds anything.
_ELEMENTS = {
    "svg", "g", "path", "circle", "ellipse", "line", "polyline", "polygon", "rect", "defs", "title", "desc",
    "linearGradient", "radialGradient", "stop", "clipPath", "mask", "use", "symbol",
}  # fmt: skip
_SHAPES = {"path", "circle", "ellipse", "line", "polyline", "polygon", "rect", "use"}
_PAINTS = ("fill", "stroke", "stop-color", "color")
_THEMED = {"currentcolor", "none", "inherit"}
_URL = re.compile(r"url\(\s*(['\"]?)([^)'\"]*)\1\s*\)", re.IGNORECASE)


@dataclass(frozen=True)
class PluginIcon:
    # A Lucide icon's name; "" when it's an SVG.
    name: str = ""
    # The SVG's text; "" when it's a Lucide icon.
    svg: str = ""
    # The SVG draws only in currentColor, so it takes the theme's text colour.
    mono: bool = False


def parse(value: object, folder: Path) -> PluginIcon:
    """The icon the plugin declares; empty when it declares none. Raises ValueError for a Lucide name the
    web app doesn't have, or an SVG file that's missing, too big or does more than draw."""
    declared = str(value or "").strip()
    if not declared:
        return PluginIcon()
    if declared.lower().endswith(".svg"):
        return _svg(folder, declared)
    if declared not in lucide_names():
        raise ValueError(f"its icon {declared!r} isn't a Lucide icon (lucide.dev) or an .svg file in its folder")
    return PluginIcon(name=declared)


def or_category(icon: PluginIcon, category: str) -> PluginIcon:
    """The icon, or its category's when it has none."""
    return icon if icon.name or icon.svg else PluginIcon(name=CATEGORY_ICONS.get(category, ""))


@cache
def lucide_names() -> frozenset[str]:
    return frozenset(json.loads((Path(__file__).parent / "lucide_icons.json").read_text(encoding="utf-8")))


def _svg(folder: Path, name: str) -> PluginIcon:
    path = folder / name
    inside = path.resolve().is_relative_to(folder.resolve())
    if not inside or path.is_symlink() or not path.is_file():
        raise ValueError(f"its icon {name} isn't a file in its folder")
    if path.stat().st_size > MAX_SVG_BYTES:
        raise ValueError(f"its icon {name} is bigger than {MAX_SVG_BYTES // 1024} KB")
    text = path.read_text(encoding="utf-8")
    root = _root(text, name)
    _check(root, name)
    return PluginIcon(svg=text, mono=_mono(root))


def _root(text: str, name: str) -> ET.Element:
    # No DOCTYPE, so no entities: nothing to expand or fetch while it's read.
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError(f"its icon {name} declares a DOCTYPE or entities, which an icon doesn't need")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"its icon {name} isn't readable SVG: {e}") from e
    if root.tag != f"{_SVG_NS}svg":
        raise ValueError(f"its icon {name} isn't an SVG (its root is {_local(root.tag)})")
    return root


def _check(root: ET.Element, name: str) -> None:
    """Raises ValueError for anything but drawing: scripts, handlers, other elements, outside links."""
    for element in root.iter():
        tag = _local(element.tag)
        if not element.tag.startswith(_SVG_NS) or tag not in _ELEMENTS:
            raise ValueError(f"its icon {name} has a <{tag}>, and an icon may only draw")
        for attribute, value in element.attrib.items():
            if _local(attribute).lower().startswith("on"):
                raise ValueError(f"its icon {name} has an {_local(attribute)} handler")
            if attribute in ("href", _XLINK_HREF) and not value.startswith("#"):
                raise ValueError(f"its icon {name} links outside itself ({value})")
            if any(not target.startswith("#") for _, target in _URL.findall(value)):
                raise ValueError(f"its icon {name} uses something outside itself ({value})")


def _mono(root: ET.Element) -> bool:
    """It paints only in currentColor (or nothing), so the theme's colour can replace it: every shape's
    fill and stroke, as inherited, and every gradient stop."""
    return _paints_themed(root, {"fill": "black", "stroke": "none"}) and any(
        "currentcolor" in value for element in root.iter() for value in _paints(element).values()
    )


def _paints_themed(element: ET.Element, inherited: dict[str, str]) -> bool:
    paints = inherited | {k: v for k, v in _paints(element).items() if k in ("fill", "stroke")}
    tag = _local(element.tag)
    if tag == "stop" and _paints(element).get("stop-color", "black") not in _THEMED:
        return False
    if tag in _SHAPES and any(paints[p] not in _THEMED for p in ("fill", "stroke")):
        return False
    return all(_paints_themed(child, paints) for child in element)


def _paints(element: ET.Element) -> dict[str, str]:
    """Its paint properties, from its attributes and its inline style, lowercased."""
    found = {p: element.attrib[p].strip().lower() for p in _PAINTS if p in element.attrib}
    for declaration in element.attrib.get("style", "").split(";"):
        prop, _, value = declaration.partition(":")
        if prop.strip().lower() in _PAINTS and value.strip():
            found[prop.strip().lower()] = value.strip().lower()
    return found


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
