"""Reading the Mac clipboard for Ctrl+V, with osascript and pbpaste faked."""

import pytest

from assistant.client import clipboard

_PNG = bytes.fromhex("89504E470D0A1A0A")


def _fake(monkeypatch, kinds, outputs=None, fail=False):
    async def run(*command):
        if fail:
            raise clipboard.ClipboardError("Couldn't read the clipboard: no access")
        if command[0] == "pbpaste":
            return "copied text"
        script = command[-1]
        return kinds if script == "clipboard info" else (outputs or {})[script]

    monkeypatch.setattr(clipboard, "_run", run)


async def test_a_copied_file_wins_over_its_icon(monkeypatch, tmp_path):
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF")
    script = "POSIX path of (the clipboard as «class furl»)"
    _fake(monkeypatch, "«class furl», 34, «class PNGf», 1000", {script: f"{report}\n"})
    pasted = await clipboard.paste()
    assert not isinstance(pasted, str)
    assert (pasted.name, pasted.media_type, pasted.data) == ("report.pdf", "application/pdf", b"%PDF")


async def test_a_screenshot_becomes_a_png(monkeypatch):
    script = "the clipboard as «class PNGf»"
    _fake(monkeypatch, "«class PNGf», 8, TIFF picture, 90", {script: f"«data PNGf{_PNG.hex().upper()}»\n"})
    pasted = await clipboard.paste()
    assert not isinstance(pasted, str)
    assert pasted.media_type == "image/png" and pasted.data == _PNG and pasted.name.endswith(".png")


async def test_text_is_returned_as_text(monkeypatch):
    _fake(monkeypatch, "Unicode text, 11, string, 11")
    assert await clipboard.paste() == "copied text"


async def test_errors_are_reported(monkeypatch):
    _fake(monkeypatch, "", fail=True)
    with pytest.raises(clipboard.ClipboardError):
        await clipboard.paste()


async def test_copy_uses_the_systems_clipboard_command(monkeypatch):
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert clipboard._copy_command() is None  # a server without a desktop
    monkeypatch.setattr(clipboard.sys, "platform", "darwin")
    assert clipboard._copy_command() == ["pbcopy"]
