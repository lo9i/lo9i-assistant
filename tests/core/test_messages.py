"""send_message: the agent reaches the user on another channel through the service's outbox."""

from assistant.core.outbox import DeliveryError
from tests.conftest import collect


class _Sender:
    def __init__(self, error: str = "") -> None:
        self.sent: list[str] = []
        self._error = error

    async def send(self, text: str) -> None:
        if self._error:
            raise DeliveryError(self._error)
        self.sent.append(text)


async def _send(service, script, **args) -> str:
    script.call("send_message", **args).reply("done")
    events = await collect(service.send(await service.session("owner", "cli"), "message me"))
    return events[1].output


async def test_sends_through_the_registered_channel(service, script):
    sender = _Sender()
    service.outbox.register("telegram", sender)
    assert await _send(service, script, text="Stretch!", channel="telegram") == "Sent on telegram."
    assert sender.sent == ["Stretch!"]


async def test_reports_channels_that_cant_deliver(service, script):
    assert (
        await _send(service, script, text="hi", channel="telegram")
        == "Can't send on telegram right now (available: none)."
    )
    service.outbox.register("telegram", _Sender("No Telegram account is paired yet."))
    assert await _send(service, script, text="hi", channel="telegram") == "No Telegram account is paired yet."
