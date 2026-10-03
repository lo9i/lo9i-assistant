"""Mail providers to pick from when connecting email, so the user types only their address and a
password. Clients offer "Other" for entering the servers by hand."""

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
    # False while the provider can't connect with a password; `password_help` says why.
    supported: bool = True


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
        "microsoft",
        "Outlook.com / Microsoft 365",
        "",
        0,
        "",
        "Not supported yet: Microsoft only allows OAuth sign-in, which the assistant can't do yet.",
        "",
        supported=False,
    ),
]


def imap_host_for(smtp_host: str) -> str:
    """The IMAP server of the provider that uses this SMTP server, or "" for another server."""
    return next((p.imap_host for p in PROVIDERS if p.host and p.host == smtp_host), "")
