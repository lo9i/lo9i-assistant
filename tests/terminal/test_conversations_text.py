from assistant.core.agent import Conversation
from assistant_terminal.conversations_text import preview


def _conversation(tags: list[str]) -> Conversation:
    return Conversation("t1", "Ferro's next match", "2026-10-09T10:00:00+00:00", "2026-10-09T11:00:00+00:00", tags=tags)


def test_the_preview_shows_the_tags() -> None:
    assert "Tags: ferro, primera nacional" in preview(_conversation(["ferro", "primera nacional"]), [])


def test_a_conversation_without_tags_shows_no_tags_line() -> None:
    assert "Tags:" not in preview(_conversation([]), [])
