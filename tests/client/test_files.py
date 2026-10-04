"""Files attached by path: dropped on a terminal window, which pastes their paths."""

from pathlib import Path

from assistant.client.files import dropped_paths, save_download


def test_pasted_paths_of_existing_files_are_files(tmp_path: Path):
    photo, note = tmp_path / "My Photo.png", tmp_path / "note.txt"
    photo.write_bytes(b"png")
    note.write_text("hi")
    escaped = str(photo).replace(" ", "\\ ")
    assert dropped_paths(f"{escaped} ") == [photo]
    assert dropped_paths(f"'{photo}' '{note}'") == [photo, note]
    assert dropped_paths(f"file://{str(photo).replace(' ', '%20')}") == [photo]


def test_anything_else_is_text(tmp_path: Path):
    note = tmp_path / "note.txt"
    note.write_text("hi")
    assert dropped_paths("hello there") == []
    assert dropped_paths(f"{note} and more") == []
    assert dropped_paths(str(tmp_path)) == []  # a folder
    assert dropped_paths("it's") == []  # unbalanced quote
    assert dropped_paths("") == []


def test_a_download_never_overwrites(tmp_path: Path):
    assert save_download("notes.txt", b"a", tmp_path) == tmp_path / "notes.txt"
    assert save_download("notes.txt", b"b", tmp_path) == tmp_path / "notes (2).txt"
    assert save_download("../../etc/passwd", b"c", tmp_path) == tmp_path / "passwd"
    assert (tmp_path / "notes.txt").read_bytes() == b"a"
