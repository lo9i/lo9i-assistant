"""Email settings and send_email: allowlisted recipients go straight out, others need approval."""

import certifi
import pytest

import assistant.core.integrations.email as email
from assistant.core.agent import EmailError
from assistant.core.events import ApprovalRequired
from assistant.core.tools.approval import UNATTENDED_DENIAL
from tests.conftest import collect


@pytest.fixture
def smtp(monkeypatch):
    sent = []

    async def verify(config):
        if config.password != "right":
            raise EmailError("Couldn't log in to smtp.test:587: bad password")

    async def send(config, to, subject, body):
        sent.append((to, subject, body))

    monkeypatch.setattr(email, "verify", verify)
    monkeypatch.setattr(email, "send", send)
    return sent


async def _connect(service):
    return await service.connect_email("smtp.test", 587, "me", "right", "me@test.com")


async def test_connect_checks_the_login_and_hides_the_password(service, smtp):
    with pytest.raises(EmailError):
        await service.connect_email("smtp.test", 587, "me", "wrong", "me@test.com")
    status = await _connect(service)
    assert status.connected and not hasattr(status, "password")
    status = await service.set_email_recipients(["Friend@Test.com", ""])
    assert status.allowed_recipients == ["friend@test.com"]


async def test_allowlisted_recipients_need_no_approval(service, script, smtp):
    await _connect(service)
    script.call("send_email", to=["me@test.com"], subject="News", body="hi").reply("sent")
    await collect(service.send(await service.session("u", "cli"), "email me"))
    assert smtp == [(["me@test.com"], "News", "hi")]


async def test_other_recipients_need_approval_and_are_denied_unattended(service, script, smtp):
    await _connect(service)
    script.call("send_email", to=["stranger@x.com"], subject="S", body="b")
    events = await collect(service.send(await service.session("u", "cli"), "email them"))
    assert any(isinstance(e, ApprovalRequired) and "stranger@x.com" in e.request["reason"] for e in events)
    script.call("send_email", to=["stranger@x.com"], subject="S", body="b").reply("could not")
    events = await collect(service.send(await service.session("u", "worker"), "email them"))
    assert events[1].output.startswith(UNATTENDED_DENIAL) and smtp == []


async def test_send_email_without_setup(service, script):
    script.call("send_email", to=["a@b.com"], subject="S", body="b").reply("ok")
    events = await collect(service.send(await service.session("u", "cli"), "email"))
    assert "isn't set up" in events[1].output


def test_tls_trusts_certifis_authorities_not_pythons_defaults():
    """Python from python.org has no certificate authorities of its own on macOS."""
    assert email._connection(email.EmailConfig(host="smtp.gmail.com"))["cert_bundle"] == certifi.where()
