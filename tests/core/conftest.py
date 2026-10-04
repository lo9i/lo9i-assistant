import pytest

import assistant.core.integrations.email.smtp as sending
from assistant.core.agent import EmailError


@pytest.fixture
def smtp(monkeypatch):
    """Sending mail without a server: "right" is the only password that logs in; sent mail is listed."""
    sent = []

    async def verify(config):
        if config.password != "right":
            raise EmailError("Couldn't log in to smtp.test:587: bad password")

    async def send(config, to, subject, body):
        sent.append((config.sender, to, subject, body))

    monkeypatch.setattr(sending, "verify", verify)
    monkeypatch.setattr(sending, "send", send)
    return sent
