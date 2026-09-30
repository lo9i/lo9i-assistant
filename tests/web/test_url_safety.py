import pytest

from assistant.core.config import settings
from assistant.core.web.policy import BlockedDomainError, check_allowed
from assistant.core.web.url_safety import UnsafeUrlError, check_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8765/",
        "http://localhost/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://1.1.1.1/",
    ],
)
async def test_private_internal_and_non_http_urls_are_refused(url):
    with pytest.raises(UnsafeUrlError):
        await check_url(url)


async def test_public_ip_is_allowed():
    await check_url("http://1.1.1.1/")


def test_blocklist_covers_subdomains(monkeypatch):
    monkeypatch.setattr(settings, "web_blocked_domains", ["example.org"])
    for url in ["https://example.org/x", "https://sub.example.org/x"]:
        with pytest.raises(BlockedDomainError):
            check_allowed(url)
    check_allowed("https://notexample.org/")
