from assistant.core.integrations.email import oauth


def _sign_in(address):
    return oauth.new_sign_in("microsoft", "cid", "", "http://x/cb", address, "", "")


def test_hotmail_uses_consumers():
    url = oauth.authorization_url(_sign_in("someone@hotmail.com"), "s")
    assert url.startswith("https://login.microsoftonline.com/consumers/")


def test_work_address_uses_common():
    url = oauth.authorization_url(_sign_in("someone@enlyft.com"), "s")
    assert url.startswith("https://login.microsoftonline.com/common/")


def test_old_tokens_load_without_personal():
    t = oauth.Tokens.from_secret('{"provider":"microsoft","client_id":"c","client_secret":"","refresh_token":"r"}')
    assert t.personal is False
