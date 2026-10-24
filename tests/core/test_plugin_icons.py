"""A plugin's icon (core/repositories/icons.py): a Lucide icon by name or an SVG file of its own, checked when
the repository is read, else its category's. How it reaches the listing and an installed server is in
test_repositories.py."""

import pytest

from assistant.core.repositories import icons
from assistant.core.repositories.icons import PluginIcon

LUCIDE_LIKE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor">'
    '<path d="m17 2-5 5-5-5"/><rect width="20" height="15" x="2" y="7" rx="2"/></svg>'
)
BRAND = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><defs><linearGradient id="g">'
    '<stop offset="0" stop-color="#2AABEE"/></linearGradient></defs>'
    '<circle cx="12" cy="12" r="12" fill="url(#g)"/><path fill="#fff" d="M5 12l14-6-3 14z"/></svg>'
)


def _svg(tmp_path, text: str, name: str = "icon.svg") -> PluginIcon:
    (tmp_path / name).write_text(text)
    return icons.parse(name, tmp_path)


def test_a_lucide_name_or_none_and_the_categorys_instead(tmp_path):
    assert icons.parse("tv", tmp_path) == PluginIcon(name="tv")
    assert icons.parse(None, tmp_path) == PluginIcon()
    assert icons.or_category(PluginIcon(), "apps/media") == PluginIcon(name="clapperboard")
    assert icons.or_category(PluginIcon(name="tv"), "apps/media") == PluginIcon(name="tv")
    assert set(icons.CATEGORY_ICONS.values()) <= icons.lucide_names()
    with pytest.raises(ValueError, match="'not-an-icon' isn't a Lucide icon"):
        icons.parse("not-an-icon", tmp_path)


def test_an_svg_that_draws_in_currentcolor_takes_the_themes_colour_and_a_logo_keeps_its_own(tmp_path):
    assert _svg(tmp_path, LUCIDE_LIKE) == PluginIcon(svg=LUCIDE_LIKE, mono=True)
    assert _svg(tmp_path, BRAND) == PluginIcon(svg=BRAND, mono=False)
    # Unpainted shapes are black: not the theme's colour.
    plain = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>'
    assert not _svg(tmp_path, plain).mono
    styled = '<svg xmlns="http://www.w3.org/2000/svg"><path style="fill: currentColor" d="M0 0h1v1z"/></svg>'
    assert _svg(tmp_path, styled).mono


@pytest.mark.parametrize(
    ("svg", "problem"),
    [
        ('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "has a <script>"),
        ('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', "has an onload handler"),
        ('<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>', "has a <foreignObject>"),
        ('<svg xmlns="http://www.w3.org/2000/svg"><style>path{}</style></svg>', "has a <style>"),
        (
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="http://www.w3.org/1999/xlink">'
            '<use x:href="https://example.com/a.svg#i"/></svg>',
            "links outside itself",
        ),
        ('<svg xmlns="http://www.w3.org/2000/svg"><path fill="url(https://x.com/p)"/></svg>', "outside itself"),
        ('<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>', "DOCTYPE"),
        ("<html/>", "isn't an SVG"),
        ("<svg", "isn't readable SVG"),
    ],
)
def test_an_svg_that_does_more_than_draw_is_refused(tmp_path, svg, problem):
    with pytest.raises(ValueError, match=problem):
        _svg(tmp_path, svg)


def test_an_svg_must_be_a_small_file_in_the_plugins_folder(tmp_path):
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (tmp_path / "outside.svg").write_text(LUCIDE_LIKE)
    (plugin / "link.svg").symlink_to(tmp_path / "outside.svg")
    for name in ("../outside.svg", "link.svg", "missing.svg"):
        with pytest.raises(ValueError, match="isn't a file in its folder"):
            icons.parse(name, plugin)
    (plugin / "big.svg").write_text(LUCIDE_LIKE.replace("<path", "<path d='" + "M0 0" * 9000 + "'/><path", 1))
    with pytest.raises(ValueError, match="bigger than 32 KB"):
        icons.parse("big.svg", plugin)
