from assistant.core.config import settings
from assistant.core.web.results import Page
from assistant.core.web.truncate import fit


def test_short_pages_are_returned_whole():
    assert fit(Page("https://x", "t", "short")) == "short"


def test_long_pages_keep_head_and_tail_and_save_the_full_text(monkeypatch, isolated_settings):
    monkeypatch.setattr(settings, "web_extract_max_chars", 1000)
    text = "HEAD" + "x" * 5000 + "TAIL"
    out = fit(Page("https://x/page", "Title", text))
    assert out.startswith("HEAD") and out.endswith("TAIL") and "characters omitted" in out
    saved = list((isolated_settings / "workspace" / "web").glob("*.md"))
    assert len(saved) == 1 and text in saved[0].read_text()
