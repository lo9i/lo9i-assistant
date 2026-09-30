from assistant.gateways.telegram.approvals import parse_decision
from assistant.gateways.telegram.formatting import split_text, to_markdown_v2


def test_parse_decision():
    assert parse_decision("a:abc") == ("abc", {"approved": True, "reason": None})
    rejected = parse_decision("r:abc")
    assert rejected is not None and rejected[1]["approved"] is False
    assert parse_decision("junk") is None


def test_split_text_respects_the_limit():
    parts = split_text("para one\n\n" + "x" * 5000 + "\n\nend", limit=3500)
    assert all(len(p) <= 3500 for p in parts) and "".join(parts).replace("\n", "").endswith("end")


def test_markdown_v2_escapes():
    assert to_markdown_v2("**bold** 1.5 `code`") == "*bold* 1\\.5 `code`"
