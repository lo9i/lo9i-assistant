"""The answer buttons' marker: taken out of what the user reads, also while the reply streams."""

from assistant.core.conversation import choices


def test_the_marker_at_the_end_is_taken_out():
    text = "Should I commit and push?\n\n<!-- choices: Push | Commit only | Cancel -->"
    assert choices.without_markers(text).strip() == "Should I commit and push?"


def test_a_marker_still_streaming_is_held_back():
    assert choices.without_markers("Push it?\n<!-- choices: Ye") == "Push it?\n"
    assert choices.without_markers("Push it?\n<!-") == "Push it?\n"


def test_other_comments_and_text_stay():
    assert choices.without_markers("a <!-- note --> b <!-- CHOICES: x --> c") == "a <!-- note --> b  c"
    assert choices.without_markers("1 < 2") == "1 < 2"


def test_a_streamed_reply_shows_everything_but_the_marker():
    streamed = choices.Streamed()
    parts = ["Push it?", "\n\n<!", "-- choices:", " Yes | No -->", " ok"]
    assert [streamed.add(part) for part in parts] == ["Push it?", "\n\n", "", "", " ok"]


def test_a_comment_that_isnt_a_marker_shows_once_it_closes():
    streamed = choices.Streamed()
    assert [streamed.add(part) for part in ["a <!-- no", "te --> b"]] == ["a ", "<!-- note --> b"]
