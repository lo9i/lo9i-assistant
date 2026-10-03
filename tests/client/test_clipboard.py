"""Reading the clipboard for Ctrl+V, with osascript, pbpaste, wl-paste and xclip faked."""

import pytest

from assistant.client import clipboard
from assistant.client.clipboard import linux, process

_PNG = bytes.fromhex("89504E470D0A1A0A")


def _fake_mac(monkeypatch, kinds, outputs=None, fail=False):
    async def run(*command):
        if fail:
            raise clipboard.ClipboardError("Couldn't read the clipboard: no access")
        if command[0] == "pbpaste":
            return b"copied text"
        script = command[-1]
        return (kinds if script == "clipboard info" else (outputs or {})[script]).encode()

    monkeypatch.setattr(clipboard.sys, "platform", "darwin")
    monkeypatch.setattr(process, "run", run)


def _fake_linux(monkeypatch, reader, outputs):
    """outputs maps a type to its contents; None reads the text."""
    commands = {reader.list_types: "\n".join(t for t in outputs if t).encode()}
    commands |= {reader.read_as(t) if t else reader.read: data for t, data in outputs.items()}

    async def run(*command):
        return commands[command]

    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setattr(linux, "find_reader", lambda: reader)
    monkeypatch.setattr(process, "run", run)


async def test_a_copied_file_wins_over_its_icon(monkeypatch, tmp_path):
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF")
    script = "POSIX path of (the clipboard as «class furl»)"
    _fake_mac(monkeypatch, "«class furl», 34, «class PNGf», 1000", {script: f"{report}\n"})
    pasted = await clipboard.paste()
    assert not isinstance(pasted, str)
    assert (pasted.name, pasted.media_type, pasted.data) == ("report.pdf", "application/pdf", b"%PDF")


async def test_a_screenshot_becomes_a_png(monkeypatch):
    script = "the clipboard as «class PNGf»"
    _fake_mac(monkeypatch, "«class PNGf», 8, TIFF picture, 90", {script: f"«data PNGf{_PNG.hex().upper()}»\n"})
    pasted = await clipboard.paste()
    assert not isinstance(pasted, str)
    assert pasted.media_type == "image/png" and pasted.data == _PNG and pasted.name.endswith(".png")


async def test_text_is_returned_as_text(monkeypatch):
    _fake_mac(monkeypatch, "Unicode text, 11, string, 11")
    assert await clipboard.paste() == "copied text"


async def test_errors_are_reported(monkeypatch):
    _fake_mac(monkeypatch, "", fail=True)
    with pytest.raises(clipboard.ClipboardError):
        await clipboard.paste()


@pytest.mark.parametrize("reader", [linux._WAYLAND, linux._X11])
async def test_linux_a_copied_file_wins_over_its_icon(monkeypatch, tmp_path, reader):
    report = tmp_path / "my report.pdf"
    report.write_bytes(b"%PDF")
    uris = f"# copied\r\nfile://{str(report).replace(' ', '%20')}\r\n".encode()
    _fake_linux(monkeypatch, reader, {"text/uri-list": uris, "image/png": _PNG})
    pasted = await clipboard.paste()
    assert not isinstance(pasted, str)
    assert (pasted.name, pasted.data) == ("my report.pdf", b"%PDF")


async def test_linux_a_copied_link_is_not_a_file(monkeypatch):
    outputs = {"text/uri-list": b"https://example.com\n", "text/plain": b"", None: b"https://example.com"}
    _fake_linux(monkeypatch, linux._WAYLAND, outputs)
    assert await clipboard.paste() == "https://example.com"


async def test_linux_a_screenshot_becomes_a_png(monkeypatch):
    _fake_linux(monkeypatch, linux._X11, {"UTF8_STRING": b"", "image/png": _PNG})
    pasted = await clipboard.paste()
    assert not isinstance(pasted, str)
    assert pasted.media_type == "image/png" and pasted.data == _PNG


async def test_linux_text_is_returned_as_text(monkeypatch):
    _fake_linux(monkeypatch, linux._WAYLAND, {"text/plain;charset=utf-8": b"", None: b"copied text"})
    assert await clipboard.paste() == "copied text"


async def test_linux_without_a_desktop_paste_is_unavailable(monkeypatch):
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert not clipboard.available()
    with pytest.raises(clipboard.ClipboardError):
        await clipboard.paste()


def test_linux_picks_the_reader_of_the_running_desktop(monkeypatch):
    monkeypatch.setattr(linux.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert linux.find_reader() == linux._WAYLAND
    monkeypatch.delenv("WAYLAND_DISPLAY")
    assert linux.find_reader() == linux._X11


async def test_copy_uses_the_systems_clipboard_command(monkeypatch):
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert clipboard._copy_command() is None  # a server without a desktop
    monkeypatch.setattr(clipboard.sys, "platform", "darwin")
    assert clipboard._copy_command() == ["pbcopy"]
