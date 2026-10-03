"""Mail providers to pick from when connecting email, so the user types only their address and a
password, or signs in (OAuth: Google, Microsoft). Clients offer "Other" for entering the servers by
hand."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailProvider:
    id: str
    name: str
    host: str
    port: int
    # IMAP over TLS (port 993), for reading mail.
    imap_host: str
    # How to get the password this provider wants, and where.
    password_help: str
    password_url: str
    # False while the provider can't connect; `password_help` says why.
    supported: bool = True
    # Signs in with OAuth instead of a password: "google" or "microsoft" (oauth.py). Then
    # `password_help` explains registering the OAuth app, and `password_url` is where.
    oauth: str = ""


PROVIDERS = [
    EmailProvider(
        "gmail",
        "Gmail",
        "smtp.gmail.com",
        587,
        "imap.gmail.com",
        "Gmail needs an app password, not your Google password. Turn on 2-Step Verification in your "
        "Google Account, create an app password, and paste its 16 characters without spaces.",
        "https://myaccount.google.com/apppasswords",
    ),
    EmailProvider(
        "icloud",
        "iCloud Mail",
        "smtp.mail.me.com",
        587,
        "imap.mail.me.com",
        "iCloud needs an app-specific password: Sign-In and Security → App-Specific Passwords.",
        "https://account.apple.com",
    ),
    EmailProvider(
        "yahoo",
        "Yahoo Mail",
        "smtp.mail.yahoo.com",
        465,
        "imap.mail.yahoo.com",
        "Yahoo needs an app password: Account security → Generate app password.",
        "https://login.yahoo.com/account/security",
    ),
    EmailProvider(
        "aol",
        "AOL Mail",
        "smtp.aol.com",
        465,
        "imap.aol.com",
        "AOL needs an app password: Account security → Generate app password.",
        "https://login.aol.com/account/security",
    ),
    EmailProvider(
        "fastmail",
        "Fastmail",
        "smtp.fastmail.com",
        465,
        "imap.fastmail.com",
        "Fastmail needs an app password: Settings → Privacy & Security → App passwords.",
        "https://app.fastmail.com/settings/security/apps",
    ),
    EmailProvider(
        "gmail-oauth",
        "Gmail (sign in with Google)",
        "smtp.gmail.com",
        587,
        "imap.gmail.com",
        "Sign in with Google instead of an app password. It needs an OAuth app of your own: in Google "
        "Cloud Console, set up the OAuth consent screen (External, published), then create an OAuth "
        "client ID of type Web application with the redirect URI shown here, and paste its client ID "
        "and secret.",
        "https://console.cloud.google.com/apis/credentials",
        oauth="google",
    ),
    EmailProvider(
        "microsoft",
        "Outlook.com / Microsoft 365",
        "smtp.office365.com",
        587,
        "outlook.office365.com",
        "Microsoft only allows signing in, which needs an app registration of your own: in Microsoft "
        "Entra, register an app for personal and work accounts, add the redirect URI shown here as a "
        "Web redirect, create a client secret, and paste the app's client ID and the secret.",
        "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
        oauth="microsoft",
    ),
]


def imap_host_for(smtp_host: str) -> str:
    """The IMAP server of the provider that uses this SMTP server, or "" for another server."""
    return next((p.imap_host for p in PROVIDERS if p.host and p.host == smtp_host), "")
