"""Email accounts from any client: connect, change, pick the default, and where each one's new mail
is announced; and who the agent may email without asking, from any account. Passwords never leave
the daemon."""

from dataclasses import dataclass, replace

from assistant.core import accounts as core_accounts
from assistant.core.agent.channels import ChannelsMixin
from assistant.core.integrations.email import accounts, imap, oauth, recipients, smtp
from assistant.core.integrations.email import plugins as email_plugins
from assistant.core.integrations.email.accounts import EmailConfig, EmailError
from assistant.core.integrations.email.providers import EmailProvider
from assistant.core.oauth import new_state
from assistant.core.secret_store import SecretError

__all__ = ["EmailAccount", "EmailAccountNotFoundError", "EmailError", "EmailMixin", "EmailProvider"]


class EmailAccountNotFoundError(EmailError):
    pass


@dataclass
class EmailAccount:
    id: str
    label: str
    # The one tools use when the model names no account.
    default: bool
    # "ok", or "needs_sign_in" (connect it again); `problem` says why.
    status: str
    problem: str
    host: str
    port: int
    username: str
    sender: str
    # Reading mail: empty when only sending is set up.
    imap_host: str
    imap_port: int
    # A chat channel (core/agent/channels.py), or "" (no announcements).
    new_mail_alerts: str
    # "password", or "oauth" (signed in with `oauth_provider`: google, microsoft).
    auth: str = "password"
    oauth_provider: str = ""
    # The email plugin it belongs to, or "" for servers entered by hand.
    plugin: str = ""


_LABEL_CHARS = 60


class EmailMixin(ChannelsMixin):
    async def email_providers(self) -> list[EmailProvider]:
        """Providers clients offer to pick from: the presets of the email plugins that are on."""
        return await email_plugins.providers(self._storage.store)

    async def email_accounts(self) -> list[EmailAccount]:
        """The default first."""
        return [_account(c) for c in await accounts.list_accounts(self._storage.store)]

    async def add_email_account(
        self,
        label: str,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        imap_host: str = "",
        imap_port: int = 993,
        plugin: str = "",
    ) -> EmailAccount:
        """Check the logins with the servers (IMAP too when given), then save, as an account of
        `plugin` ("" for servers entered by hand). The first account becomes the default. Raises
        EmailError."""
        await self._check_plugin(plugin)
        config = EmailConfig(
            host.strip(), port, username.strip(), password, sender.strip(), imap_host.strip(), imap_port
        )
        config.label, config.plugin = label, plugin
        return await self._verified_save(config, password)

    async def update_email_account(
        self,
        account_id: str,
        label: str,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        imap_host: str = "",
        imap_port: int = 993,
    ) -> EmailAccount:
        """Change an account's sign-in. An empty password keeps the saved one. Raises EmailError."""
        current = await self._email(account_id)
        if not password:
            current = await accounts.load(self._storage.store, self.secrets, account_id)
        config = EmailConfig(
            host.strip(),
            port,
            username.strip(),
            password or current.password,
            sender.strip(),
            imap_host.strip(),
            imap_port,
            current.new_mail_alerts,
        )
        config.account_id, config.label, config.default = account_id, label, current.default
        config.plugin = current.plugin
        return await self._verified_save(config, config.password)

    async def start_email_sign_in(
        self,
        provider: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        address: str,
        label: str = "",
        account_id: str = "",
        plugin: str = "",
    ) -> str:
        """The provider's sign-in page for a new account of `plugin`, or `account_id` signing in
        again. The browser comes back to `redirect_uri` (the web app's /app/oauth), which calls
        finish_sign_in. Raises EmailError."""
        await self._check_plugin(plugin)
        if account_id:
            await self._email(account_id)
            if not client_id.strip():
                client_id, client_secret = await self._saved_oauth_app(account_id)
        sign_in = oauth.new_sign_in(provider, client_id, client_secret, redirect_uri, address, label, account_id)
        sign_in = replace(sign_in, plugin=plugin)
        state = new_state()
        self._sign_ins.add(state, sign_in)
        return oauth.authorization_url(sign_in, state)

    async def _saved_oauth_app(self, account_id: str) -> tuple[str, str]:
        """The client id and secret an account signed in with, to sign in again without typing them;
        empty when they can't be read."""
        account = await core_accounts.get(self._storage.store, accounts.KIND, account_id)
        try:
            secret = await core_accounts.secret(self._storage.store, self.secrets, account) if account else ""
            tokens = oauth.Tokens.from_secret(secret)
        except (SecretError, ValueError, TypeError):
            return "", ""
        return tokens.client_id, tokens.client_secret

    async def _finish_email_sign_in(self, sign_in: oauth.SignIn, code: str) -> EmailAccount:
        """Trade the code for tokens, check both servers with them, and save the account. Raises EmailError."""
        tokens = await oauth.exchange(sign_in, code)
        config = await self._signed_in_config(sign_in, tokens.access_token)
        return await self._verified_save(config, tokens.to_secret())

    async def _signed_in_config(self, sign_in: oauth.SignIn, access_token: str) -> EmailConfig:
        provider = oauth.provider_for(sign_in.provider)
        config = EmailConfig(provider.smtp_host, provider.smtp_port, sign_in.address, access_token, sign_in.address)
        config.imap_host, config.auth, config.oauth_provider = provider.imap_host, "oauth", provider.id
        config.label, config.plugin = sign_in.label, sign_in.plugin
        if sign_in.account_id:
            current = await self._email(sign_in.account_id)
            config.account_id, config.label, config.default = current.account_id, current.label, current.default
            config.new_mail_alerts, config.plugin = current.new_mail_alerts, current.plugin
        return config

    async def rename_email_account(self, account_id: str, label: str) -> EmailAccount:
        """Change only the name; the sign-in stays. Empty goes back to the address. Raises EmailError."""
        config = await self._email(account_id)
        config.label = label.strip()[:_LABEL_CHARS] or config.sender
        await self._check_label(config)
        return _account(await accounts.save(self._storage.store, self.secrets, config))

    async def set_default_email_account(self, account_id: str) -> EmailAccount:
        await self._email(account_id)
        await accounts.make_default(self._storage.store, account_id)
        return _account(await self._email(account_id))

    async def set_new_mail_alerts(self, account_id: str, channel: str) -> EmailAccount:
        """Announce the account's new mail on an installed chat channel, or nowhere (""). Raises EmailError."""
        config = await self._email(account_id)
        installed = await self.channel_names()
        if channel and channel not in installed:
            raise EmailError(
                f"New mail can be announced on {' or '.join(installed) or 'an installed chat channel'}, not {channel}."
            )
        if channel and not config.can_read:
            raise EmailError("Set up reading mail first: connect the account again with its IMAP server.")
        config.new_mail_alerts = channel
        return _account(await accounts.save(self._storage.store, self.secrets, config))

    async def email_recipients(self) -> list[str]:
        """Who the agent may email without asking, besides the user's own accounts."""
        return await recipients.get(self._storage.store)

    async def set_email_recipients(self, addresses: list[str]) -> list[str]:
        return await recipients.save(self._storage.store, addresses)

    async def remove_email_account(self, account_id: str) -> None:
        """Another account becomes the default if this one was."""
        await self._email(account_id)
        await accounts.remove(self._storage.store, account_id)

    async def _email(self, account_id: str) -> EmailConfig:
        """The account without its password. Raises EmailAccountNotFoundError."""
        config = await accounts.get(self._storage.store, account_id)
        if config is None:
            raise EmailAccountNotFoundError(f"No email account {account_id}.")
        return config

    async def _check_plugin(self, plugin: str) -> None:
        """An account belongs to an email plugin that is on, or to none (servers entered by hand)."""
        if plugin and plugin not in await email_plugins.active(self._storage.store):
            raise EmailError(f"{plugin} isn't an email plugin that's installed and on.")

    async def _check_label(self, config: EmailConfig) -> None:
        """Names are unique: the agent picks an account by its name."""
        others = await accounts.list_accounts(self._storage.store)
        taken = {c.label.lower() for c in others if c.account_id != config.account_id}
        if (config.label or config.sender).lower() in taken:
            raise EmailError(f"Another account is already called {config.label or config.sender}.")

    async def _verified_save(self, config: EmailConfig, password: str) -> EmailAccount:
        config.label = config.label.strip()[:_LABEL_CHARS]
        await self._check_label(config)
        await smtp.verify(config)
        if config.imap_host:
            await imap.verify(config)
        return _account(await accounts.save(self._storage.store, self.secrets, config, password))


def _account(config: EmailConfig) -> EmailAccount:
    return EmailAccount(
        config.account_id,
        config.label,
        config.default,
        config.status,
        config.problem,
        config.host,
        config.port,
        config.username,
        config.sender,
        config.imap_host,
        config.imap_port,
        config.new_mail_alerts,
        config.auth,
        config.oauth_provider,
        config.plugin,
    )
