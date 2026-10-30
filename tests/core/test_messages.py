"""send_message: the agent reaches the user on another channel through the service's outbox."""

from assistant.core.outbox import DeliveryError
from tests.conftest import collect


class _Sender:
    def __init__(self, error: str = "") -> None:
        self.sent: list[str] = []
        self._error = error

    async def send(self, text: str) -> list[str]:
        if self._error:
            raise DeliveryError(self._error)
        self.sent.append(text)
        return [f"m{len(self.sent)}"]


async def _send(service, script, **args) -> str:
    script.call("send_message", **args).reply("done")
    events = await collect(service.send(await service.session("owner", "cli"), "message me"))
    return events[1].output


async def test_sends_through_the_registered_channel(service, script):
    sender = _Sender()
    service.outbox.register("telegram", sender)
    assert await _send(service, script, text="Stretch!", channel="telegram") == "Sent on telegram."
    assert sender.sent == ["Stretch!"]


async def test_replying_to_a_message_sent_from_a_conversation_goes_on_there(service, script):
    service.outbox.register("telegram", _Sender())
    await _send(service, script, text="Stretch!", channel="telegram")
    inbox = (await service.session("owner", "cli")).thread_id
    assert await service.chat_message_thread("owner", "telegram", "42", "m1") == inbox  # in the user's chat 42


async def test_replying_to_any_paired_accounts_copy_goes_on_there(service, script):
    """Telegram sends it to every paired account, where each copy has an id of its own."""

    class _Copies(_Sender):
        async def send(self, text: str) -> list[str]:
            return ["m1", "n1"]

    service.outbox.register("telegram", _Copies())
    await _send(service, script, text="Stretch!", channel="telegram")
    inbox = (await service.session("owner", "cli")).thread_id
    for chat, message in (("42", "m1"), ("77", "n1")):
        assert await service.chat_message_thread("owner", "telegram", chat, message) == inbox


async def test_reports_channels_that_cant_deliver(service, script):
    assert (
        await _send(service, script, text="hi", channel="telegram")
        == "Can't send on telegram right now (available: none)."
    )
    service.outbox.register("telegram", _Sender("No Telegram account is paired yet."))
    assert await _send(service, script, text="hi", channel="telegram") == "No Telegram account is paired yet."
