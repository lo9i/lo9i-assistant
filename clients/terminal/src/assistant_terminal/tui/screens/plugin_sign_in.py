"""A plugin's sign-in with the user's own OAuth app (`oauth:` in its server.yaml; the daemon's
core/mcp/plugin_oauth.py), opened from /plugins or from its setup in a conversation: whether it's signed in and as
whom, signing in and signing out. Signing in opens the provider's page in a browser, which comes back to the daemon's
web app on this computer and finishes it, or the user pastes the address it ended on."""

import webbrowser
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown

from assistant.client.daemon_client import McpApi, OAuthApi
from assistant.core.agent import McpServerError, SignInError
from assistant_terminal.i18n import t
from assistant_terminal.sign_in_text import MISSING_CODE, PASTE_HINT, REDIRECT, returned, signing_message
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_PROVIDERS = {"google": "Google"}


class PluginSignInScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", t("Close"))]
    # A sign-in finished in the browser saves the plugin again, which the daemon reports as `mcp`.
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"mcp"})

    def __init__(self, mcp: McpApi, oauth: OAuthApi, plugin: str, provider: str) -> None:
        super().__init__()
        self._mcp, self._oauth = mcp, oauth
        self._plugin = plugin
        self._provider = _PROVIDERS.get(provider, provider)
        self._signed_in_as = ""
        self._message = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="plugin-sign-in"):
            yield Markdown(id="plugin-sign-in-body")
            yield Input(placeholder=t("Your OAuth app's client ID"), id="plugin-client-id")
            yield Input(placeholder=t("Your OAuth app's client secret"), password=True, id="plugin-client-secret")
            yield Input(placeholder=PASTE_HINT, id="plugin-returned")
            with Horizontal(id="plugin-sign-in-buttons"):
                yield Button(t("Sign in"), variant="primary", id="sign-in")
                yield Button(t("Finish"), variant="success", id="finish")
                yield Button(t("Sign out"), variant="error", id="sign-out")
                yield Button(t("Close"), id="close")

    async def on_mount(self) -> None:
        self.query_one("#plugin-returned").display = False
        self.query_one("#finish").display = False
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the plugins change too: the browser finished the sign-in."""
        status = next((s for s in await self._mcp.servers() if s.name == self._plugin), None)
        signed_in_as = status.signed_in_as if status else ""
        if signed_in_as and signed_in_as != self._signed_in_as:
            # Signed in since the page opened: nothing left to paste.
            self._message = ""
            self.query_one("#plugin-returned").display = self.query_one("#finish").display = False
        self._signed_in_as = signed_in_as
        self.query_one("#sign-out").display = bool(signed_in_as)
        await self._show()

    async def _show(self) -> None:
        if self._signed_in_as:
            state = t("Signed in to {provider} as {account}.", provider=self._provider, account=self._signed_in_as)
        else:
            state = t(
                "Not signed in yet: {name}'s tools work once you sign in to {provider}.",
                name=self._plugin,
                provider=self._provider,
            )
        help_text = t(
            "It signs in with an OAuth app of your own: in your Google Cloud project "
            "(https://console.cloud.google.com/apis/credentials), create an OAuth client ID of type Web application "
            "with the redirect URI below, and paste its client ID and secret. Once signed in, leave them empty to "
            "sign in again with the same app."
        )
        redirect = t("Redirect URI to register: {uri}", uri=f"`{REDIRECT}`")
        parts = ["## " + t("Sign in to {provider}", provider=self._provider), state, help_text, redirect]
        await self.query_one("#plugin-sign-in-body", Markdown).update("\n\n".join([*parts, self._message]))

    @on(Button.Pressed, "#sign-in")
    @reports_daemon_unavailable
    async def _sign_in(self) -> None:
        client_id = self.query_one("#plugin-client-id", Input).value
        secret = self.query_one("#plugin-client-secret", Input).value
        try:
            url = await self._mcp.start_plugin_sign_in(self._plugin, REDIRECT, client_id, secret)
        except McpServerError as e:
            await self._say(f"**{e}**")
            return
        opened = webbrowser.open(url)
        self.query_one("#plugin-returned").display = self.query_one("#finish").display = True
        await self._say(signing_message(url, opened, t("it shows as signed in here")))

    @on(Button.Pressed, "#finish")
    @reports_daemon_unavailable
    async def _finish(self) -> None:
        state, code = returned(self.query_one("#plugin-returned", Input).value)
        if not state or not code:
            await self._say(MISSING_CODE)
            return
        try:
            await self._oauth.finish(state, code)
        except (SignInError, McpServerError) as e:
            await self._say(f"**{e}**")
            return
        await self.reload()

    @on(Button.Pressed, "#sign-out")
    @reports_daemon_unavailable
    async def _sign_out(self) -> None:
        try:
            await self._mcp.sign_out_plugin(self._plugin)
        except McpServerError as e:
            await self._say(f"**{e}**")
            return
        self.notify(t("Signed out of {provider}.", provider=self._provider))
        await self.reload()

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    async def _say(self, text: str) -> None:
        self._message = text
        await self._show()
