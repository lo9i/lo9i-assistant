"""Email accounts, opened from /plugins: an email plugin's accounts, or from /email the shared settings
(the accounts whose servers were entered by hand, and who the agent emails without asking)."""

from textual.widgets import Button, Input, Markdown, Select

from assistant.core.agent import FoundServer
from assistant_terminal.tui.screens import EmailScreen, PluginsScreen
from assistant_terminal.tui.screens.email import _alert_options
from tests.terminal.conftest import wait_for


async def _open(pilot, app, client, plugin: str) -> EmailScreen:
    await pilot.pause()
    await app.push_screen(EmailScreen(client.email, client.oauth, client.channels, plugin))
    await wait_for(pilot, lambda: isinstance(app.screen, EmailScreen))
    return app.screen


def _body(screen) -> str:
    return screen.query_one("#email-body", Markdown).source


async def _add_gmail(pilot, screen, address: str, label: str = "") -> None:
    await wait_for(pilot, lambda: screen.query_one("#email-address").display)
    screen.query_one("#email-label", Input).value = label
    screen.query_one("#email-address", Input).value = address
    screen.query_one("#email-password", Input).value = "right"
    screen.query_one("#connect", Button).press()
    await wait_for(pilot, lambda: f"<{address}>" in _body(screen))


async def test_a_plugin_with_one_provider_needs_only_the_address_and_password(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app, client, "gmail")
        await wait_for(pilot, lambda: screen.query_one("#email-address").display)
        assert not screen.query_one("#email-host").display and not screen.query_one("#email-provider").display
        assert "myaccount.google.com/apppasswords" in screen.query_one("#email-help", Markdown).source
        await _add_gmail(pilot, screen, "me@gmail.com", "Personal")
        assert client.email.connected_with == (
            "Personal",
            "smtp.gmail.com",
            587,
            "me@gmail.com",
            "right",
            "me@gmail.com",
            "imap.gmail.com",
        )
        assert client.email.accounts_by_id["a1"].plugin == "gmail"
        assert "Email: Personal <me@gmail.com> · default" in _body(screen)


async def test_a_plugin_lists_only_its_own_accounts(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app, client, "gmail")
        await _add_gmail(pilot, screen, "me@gmail.com")
        await pilot.press("escape")
        other = await _open(pilot, app, client, "custom-email")
        await wait_for(pilot, lambda: "Add an email account" in _body(other))
        assert not other.query_one("#email-account").display


async def test_microsoft_signs_in_with_the_users_oauth_app(app, client, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr("assistant_terminal.tui.screens.email.webbrowser.open", lambda url: opened.append(url) or False)
    async with app.run_test(size=(110, 50)) as pilot:
        screen = await _open(pilot, app, client, "microsoft")
        help_text = screen.query_one("#email-help", Markdown)
        await wait_for(pilot, lambda: "http://localhost:" in help_text.source and "/app/oauth" in help_text.source)
        assert screen.query_one("#email-client-id").display and not screen.query_one("#email-password").display
        assert str(screen.query_one("#connect", Button).label) == "Sign in"
        screen.query_one("#email-address", Input).value = "me@outlook.com"
        screen.query_one("#email-client-id", Input).value = "client-1"
        screen.query_one("#email-client-secret", Input).value = "secret-1"
        screen.query_one("#connect", Button).press()
        await wait_for(pilot, lambda: screen.query_one("#finish").display)
        assert opened and client.email.sign_in[:3] == ("microsoft", "client-1", "secret-1")
        assert client.email.sign_in[-1] == "microsoft"
        returned = screen.query_one("#email-returned", Input)
        returned.value = "http://localhost:8765/app/oauth?code=c1&state=s1"
        screen.query_one("#finish", Button).press()
        body = screen.query_one("#email-body", Markdown)
        await wait_for(pilot, lambda: "Signed in" in body.source and "me@outlook.com" in body.source)
        [account] = client.email.accounts_by_id.values()
        assert (account.auth, account.oauth_provider, account.plugin) == ("oauth", "microsoft", "microsoft")


async def test_a_custom_provider_asks_for_the_servers(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app, client, "custom-email")
        await wait_for(pilot, lambda: screen.query_one("#email-host").display)
        assert not screen.query_one("#email-address").display
        for field, value in {
            "email-host": "smtp.test",
            "email-port": "587",
            "email-user": "me",
            "email-password": "wrong",
            "email-sender": "me@test.com",
        }.items():
            screen.query_one(f"#{field}", Input).value = value
        screen.query_one("#connect", Button).press()
        await wait_for(pilot, lambda: "bad password" in _body(screen))
        screen.query_one("#email-password", Input).value = "right"
        screen.query_one("#connect", Button).press()
        await wait_for(pilot, lambda: "Email: me@test.com" in _body(screen))
        assert client.email.accounts_by_id["a1"].plugin == "custom-email"
        assert client.email.connected_with[1:3] == ("smtp.test", 587)


async def test_email_saves_who_the_assistant_emails_without_asking(app, client):
    from assistant_terminal.tui.screens import EmailRecipientsScreen

    async with app.run_test(size=(110, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/email", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EmailRecipientsScreen))
        app.screen.query_one(Input).value = "friend@test.com"
        app.screen.query_one("#save", Button).press()
        await wait_for(pilot, lambda: client.email.allowed == ["friend@test.com"])


async def test_new_mail_alerts_are_chosen_once_mail_can_be_read(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app, client, "gmail")
        await wait_for(pilot, lambda: screen.query_one("#email-address").display)
        assert not screen.query_one("#email-alerts").display
        await _add_gmail(pilot, screen, "me@gmail.com")
        assert "Reads mail from: imap.gmail.com" in _body(screen)
        assert screen.query_one("#email-alerts").display
        screen.query_one("#email-alerts", Select).value = "telegram"
        await wait_for(pilot, lambda: client.email.accounts_by_id["a1"].new_mail_alerts == "telegram")


def test_new_mail_can_be_announced_on_installed_channels_only():
    """A channel set before its plugin was removed stays offered, so the account still shows it."""
    assert [v for _, v in _alert_options(["telegram"], "")] == ["", "telegram"]
    assert [v for _, v in _alert_options(["telegram"], "slack")] == ["", "telegram", "slack"]


async def test_a_second_account_can_become_the_default_and_be_removed(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app, client, "gmail")
        await _add_gmail(pilot, screen, "me@gmail.com", "Personal")
        screen.query_one("#email-account", Select).value = "new"
        await wait_for(pilot, lambda: "Add an email account" in _body(screen))
        await _add_gmail(pilot, screen, "me@work.com", "Work")
        assert screen.query_one("#default").display
        screen.query_one("#default", Button).press()
        await wait_for(pilot, lambda: "Work <me@work.com> · default" in _body(screen))
        screen.query_one("#remove", Button).press()
        await wait_for(pilot, lambda: "Personal <me@gmail.com> · default" in _body(screen))
        assert list(client.email.accounts_by_id) == ["a1"]


async def test_renaming_keeps_the_sign_in(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app, client, "gmail")
        await _add_gmail(pilot, screen, "me@gmail.com")
        assert screen.query_one("#email-name", Input).value == "me@gmail.com"
        screen.query_one("#email-name", Input).value = "Personal"
        screen.query_one("#rename", Button).press()
        await wait_for(pilot, lambda: "Email: Personal <me@gmail.com>" in _body(screen))
        assert client.email.connected_with[4] == "right"  # signed in once, not again


async def test_plugins_open_an_email_plugins_accounts_and_email_opens_the_shared_settings(app, client):
    gmail = FoundServer("gmail", "Gmail", "none", [], True, installed=True, category="communications/email", email=True)
    client.repositories.more = [gmail]
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/plugins", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, PluginsScreen))
        plugins = app.screen
        await wait_for(pilot, lambda: plugins.query_one("#email-accounts").display)
        assert "Kind: Email provider" in plugins.query_one("#plugin-body", Markdown).source
        plugins.query_one("#email-accounts", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, EmailScreen) and app.screen._plugin == "gmail")
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is plugins)
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is not plugins)
        assert not isinstance(app.screen, EmailScreen)
