"""Email accounts and send_email: allowlisted recipients go straight out, others need approval;
several accounts, the default, and passwords kept encrypted apart from the settings."""

import stat
from pathlib import Path

import certifi
import pytest

import assistant.core.integrations.email.smtp as sending
from assistant.core.agent import EmailAccountNotFoundError, EmailError, Session
from assistant.core.config import settings
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.conversation.prompt import build_system_prompt
from assistant.core.events import ApprovalRequired
from assistant.core.integrations.email import accounts
from assistant.core.tools.approval import UNATTENDED_DENIAL
from tests.conftest import collect


async def _add(service, sender="me@test.com", label=""):
    return await service.add_email_account(label, "smtp.test", 587, "me", "right", sender)


async def test_adding_checks_the_login_and_hides_the_password(service, smtp):
    with pytest.raises(EmailError):
        await service.add_email_account("", "smtp.test", 587, "me", "wrong", "me@test.com")
    account = await _add(service)
    assert account.default and account.label == "me@test.com" and not hasattr(account, "password")


async def test_passwords_are_encrypted_apart_with_a_private_key_file(service, smtp):
    account = await _add(service)
    records = [i.value for i in await service.store.asearch(("accounts", "email"))]
    secrets = [i.value for i in await service.store.asearch(("secrets",))]
    assert "right" not in str(records) and len(secrets) == 1 and "right" not in str(secrets)
    assert (await accounts.load(service.store, service.secrets, account.id)).password == "right"
    key = Path(settings.secrets_key_path)
    assert stat.S_IMODE(key.stat().st_mode) == 0o600


async def test_allowlisted_recipients_need_no_approval(service, script, smtp):
    await _add(service, "me@home.com")
    await _add(service, "me@work.com")
    assert await service.set_email_recipients(["Friend@Test.com", "", "friend@test.com"]) == ["friend@test.com"]
    to = ["me@home.com", "me@work.com", "friend@test.com"]
    script.call("send_email", to=to, subject="News", body="hi").reply("sent")
    await collect(service.send(await service.session("u", "worker"), "email us"))
    assert smtp == [("me@home.com", to, "News", "hi")]


async def test_other_recipients_need_approval_and_are_denied_unattended(service, script, smtp):
    await _add(service)
    script.call("send_email", to=["stranger@x.com"], subject="S", body="b")
    events = await collect(service.send(await service.session("u", "cli"), "email them"))
    assert any(isinstance(e, ApprovalRequired) and "stranger@x.com" in e.request["reason"] for e in events)
    script.call("send_email", to=["stranger@x.com"], subject="S", body="b").reply("could not")
    events = await collect(service.send(Session("u", UNATTENDED_CHANNEL, "job:mail:1"), "email them"))
    assert events[1].output.startswith(UNATTENDED_DENIAL) and smtp == []


async def test_tools_use_the_named_account_or_the_default(service, script, smtp):
    await _add(service, "me@home.com", "Personal")
    await _add(service, "me@work.com", "Work")
    script.call("send_email", to=["me@home.com"], subject="A", body="a").reply("ok")
    script.call("send_email", to=["me@work.com"], subject="B", body="b", account="work").reply("ok")
    script.call("send_email", to=["x@y.com"], subject="C", body="c", account="Gym").reply("ok")
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    events = await collect(service.send(session, "three"))
    assert [s[0] for s in smtp] == ["me@home.com", "me@work.com"]
    assert "No email account called 'Gym'" in events[1].output and "Work <me@work.com>" in events[1].output


async def test_the_default_can_change_and_passes_on_when_removed(service, smtp):
    home = await _add(service, "me@home.com", "Personal")
    work = await _add(service, "me@work.com", "Work")
    assert not work.default
    await service.set_default_email_account(work.id)
    assert [(a.label, a.default) for a in await service.email_accounts()] == [("Work", True), ("Personal", False)]
    await service.remove_email_account(work.id)
    [left] = await service.email_accounts()
    assert left.id == home.id and left.default
    assert len(await service.store.asearch(("secrets",))) == 1  # the removed account's password is gone
    with pytest.raises(EmailAccountNotFoundError):
        await service.remove_email_account(work.id)


async def test_a_password_the_key_cant_read_asks_to_connect_again(service, smtp):
    account = await _add(service)
    # As if the key file had been replaced: the saved secret no longer decrypts.
    await service.store.aput(("secrets",), f"email:{account.id}", {"value": "made-with-another-key"})
    with pytest.raises(EmailError, match="connect it again"):
        await accounts.load(service.store, service.secrets, account.id)
    [listed] = await service.email_accounts()
    assert listed.status == "needs_sign_in"
    updated = await service.update_email_account(account.id, "", "smtp.test", 587, "me", "right", "me@test.com")
    assert updated.status == "ok"


async def test_the_system_prompt_lists_the_accounts(service, smtp):
    await _add(service, "me@home.com", "Personal")
    await _add(service, "me@work.com", "Work")
    prompt = await build_system_prompt(service.store, "u", "", "")
    assert "- email: Personal <me@home.com> (default)\n- email: Work <me@work.com>" in prompt


async def test_send_email_without_setup(service, script):
    script.call("send_email", to=["a@b.com"], subject="S", body="b").reply("ok")
    events = await collect(service.send(await service.session("u", "cli"), "email"))
    assert events[1].output.startswith("No email account is connected. Call set_up_email")


def test_tls_trusts_certifis_authorities_not_pythons_defaults():
    """Python from python.org has no certificate authorities of its own on macOS."""
    assert sending._connection(accounts.EmailConfig(host="smtp.gmail.com"))["cert_bundle"] == certifi.where()


async def test_renaming_keeps_the_sign_in_and_names_stay_unique(service, smtp):
    home = await _add(service, "me@home.com")
    work = await _add(service, "me@work.com")
    renamed = await service.rename_email_account(home.id, "  Personal ")
    assert renamed.label == "Personal" and renamed.host == "smtp.test"
    assert (await accounts.load(service.store, service.secrets, "personal")).password == "right"
    with pytest.raises(EmailError, match="already called"):
        await service.rename_email_account(work.id, "personal")
    assert (await service.rename_email_account(home.id, "")).label == "me@home.com"
