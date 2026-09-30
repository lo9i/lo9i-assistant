"""LiveConversation: following the daemon's active conversation and runs from elsewhere."""

from assistant.client.live import LiveConversation
from assistant.core.agent import Session


class _Daemon:
    def __init__(self) -> None:
        self.active = "owner:a"

    async def new_thread(self, user_id: str) -> str:
        self.active = "owner:new"
        return self.active

    async def session(self, user_id: str, channel: str) -> Session:
        return Session(user_id, channel, self.active)


def _live(daemon: _Daemon | None = None) -> LiveConversation:
    return LiveConversation(daemon or _Daemon(), Session("owner", "cli", "owner:a"))


async def test_follow_switches_only_when_another_channel_started_a_conversation():
    daemon = _Daemon()
    live = _live(daemon)
    assert not await live.follow()
    daemon.active = "owner:b"
    assert await live.follow() and live.session.thread_id == "owner:b"


def test_runs_from_other_channels_in_this_conversation():
    live = _live()
    assert live.started_elsewhere({"thread_id": "owner:a", "channel": "telegram"})
    assert not live.started_elsewhere({"thread_id": "owner:a", "channel": "cli"})
    assert not live.started_elsewhere({"thread_id": "owner:x", "channel": "telegram"})


async def test_a_run_left_running_is_reported_once():
    live = _live()
    await live.start_new(leave_running=True)
    assert live.session.thread_id == "owner:new"
    assert not live.left_run_finished({"thread_id": "owner:new"})
    assert live.left_run_finished({"thread_id": "owner:a"})
    assert not live.left_run_finished({"thread_id": "owner:a"})
