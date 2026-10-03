"""Slack settings: the manifest, checking tokens with Slack, connecting, and the running state."""

import json

import pytest
from slack_sdk.errors import SlackApiError

import assistant.core.integrations.slack.connection as integration
from assistant.core.agent import SlackError

_TOKENS = ("xapp-1", "xoxb-1", "xoxp-1")


class _Response(dict):
    pass


@pytest.fixture
def fake_slack(monkeypatch):
    """auth.test answers per token; `team` lets a test put the user token in another workspace."""
    answers = {
        "xoxb-1": {"team_id": "T1", "team": "Acme", "user_id": "UBOT", "user": "lo9i"},
        "xoxp-1": {"team_id": "T1", "team": "Acme", "user_id": "U1", "user": "ani"},
        "xoxp-other": {"team_id": "T2", "team": "Other", "user_id": "U9", "user": "ani"},
    }

    async def api_call(self, method, **kwargs):
        if method == "apps.connections.open":
            if self.token != "xapp-1":
                raise SlackApiError("bad", _Response(error="invalid_auth"))
            return _Response(ok=True, url="wss://x")
        if self.token not in answers:
            raise SlackApiError("bad", _Response(error="invalid_auth"))
        return _Response(ok=True, **answers[self.token])

    monkeypatch.setattr(integration.AsyncWebClient, "api_call", api_call)


def test_manifest_uses_socket_mode_and_the_assistant_name():
    app = json.loads(integration.manifest("Max"))
    assert app["display_information"]["name"] == "Max" and app["features"]["bot_user"]["display_name"] == "Max"
    assert app["settings"]["socket_mode_enabled"] and app["settings"]["event_subscriptions"]["bot_events"] == [
        "message.im"
    ]
    assert (
        "search:read" in app["oauth_config"]["scopes"]["user"] and "files:read" in app["oauth_config"]["scopes"]["bot"]
    )
    assert app["features"]["slash_commands"][0]["command"] == "/new"


async def test_connect_checks_every_token_and_saves_the_owner(service, fake_slack):
    with pytest.raises(SlackError, match="should start with xoxb-"):
        await service.connect_slack("xapp-1", "xoxp-1", "xoxp-1")
    with pytest.raises(SlackError, match="app token: invalid_auth"):
        await service.connect_slack("xapp-bad", "xoxb-1", "xoxp-1")
    with pytest.raises(SlackError, match="different workspaces"):
        await service.connect_slack("xapp-1", "xoxb-1", "xoxp-other")
    status = await service.connect_slack(*_TOKENS)
    assert status.connected and status.team == "Acme" and status.owner_name == "ani" and not status.running
    config = await service.slack_config()
    assert (config.app_token, config.bot_token, config.user_token, config.owner_id) == (*_TOKENS, "U1")
    await service.disconnect_slack()
    assert not (await service.slack_status()).connected


async def test_running_while_the_adapter_can_deliver(service):
    class _Sender:
        async def send(self, text):
            pass

    service.outbox.register("slack", _Sender())
    assert (await service.slack_status()).running
    service.outbox.unregister("slack")
    assert not (await service.slack_status()).running


async def test_the_manifest_follows_the_assistant_name(service):
    await service.rename_assistant("Max")
    assert json.loads(await service.slack_manifest())["display_information"]["name"] == "Max"


@pytest.mark.live
async def test_slack_rejects_fake_tokens():
    with pytest.raises(SlackError, match=r"invalid_auth|not_authed"):
        await integration.verify("xapp-1-fake", "xoxb-fake", "xoxp-fake")
