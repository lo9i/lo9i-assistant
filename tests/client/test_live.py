"""LiveConversation: the conversation this client is on, and runs in it from elsewhere."""

from assistant.client.live import LiveConversation
from assistant.core.agent import Session


class _Daemon:
    async def new_thread(self, user_id: str) -> str:
        return "owner:new"

    async def resume_thread(self, user_id: str, thread_id: str) -> None:
        pass


def _live() -> LiveConversation:
    return LiveConversation(_Daemon(), Session("owner", "cli", "owner:a"), client_id="me")


def test_runs_in_this_conversation_from_anything_but_this_client():
    live = _live()
    assert live.started_elsewhere({"thread_id": "owner:a", "channel": "cli", "client_id": "other"})
    assert live.started_elsewhere({"thread_id": "owner:a", "channel": "telegram"})
    assert not live.started_elsewhere({"thread_id": "owner:a", "channel": "cli", "client_id": "me"})
    assert not live.started_elsewhere({"thread_id": "owner:x", "channel": "cli", "client_id": "other"})


async def test_a_run_left_running_is_reported_once():
    live = _live()
    await live.start_new(leave_running=True)
    assert live.session.thread_id == "owner:new"
    assert not live.left_run_finished({"thread_id": "owner:new"})
    assert live.left_run_finished({"thread_id": "owner:a"})
    assert not live.left_run_finished({"thread_id": "owner:a"})


async def test_resume_moves_to_the_conversation():
    live = _live()
    await live.resume("owner:b")
    assert live.session.thread_id == "owner:b"
