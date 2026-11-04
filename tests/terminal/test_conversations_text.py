from assistant.core.agent import Conversation
from assistant_terminal.conversations_text import matching, message_search, preview


def _conversation(tags: list[str]) -> Conversation:
    return Conversation("t1", "Ferro's next match", "2026-10-09T10:00:00+00:00", "2026-10-09T11:00:00+00:00", tags=tags)


def test_the_preview_shows_the_tags() -> None:
    assert "Tags: ferro, primera nacional" in preview(_conversation(["ferro", "primera nacional"]), [])


def test_a_conversation_without_tags_shows_no_tags_line() -> None:
    assert "Tags:" not in preview(_conversation([]), [])


def test_a_search_matches_titles_and_what_the_daemon_found_in_messages():
    at = "2030-01-01T09:00:00+00:00"
    listed = [Conversation("owner:a", "Taxes 2030", at, at), Conversation("owner:b", "Trip", at, at)]
    assert matching(listed, "  ", set()) == listed
    assert [c.thread_id for c in matching(listed, "TAX", set())] == ["owner:a"]
    assert [c.thread_id for c in matching(listed, "rome", {"owner:b"})] == ["owner:b"]
    assert message_search("z") == "" and matching(listed, "z", {"owner:b"}) == []
