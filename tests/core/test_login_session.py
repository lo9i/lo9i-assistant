"""A daemon started at boot on macOS runs outside the user's login session: plugins that ask for the session get the
session helper's socket, and plugins that ask for the ssh agent get the link the helper keeps to the session's. A
daemon in the session gives neither: they open apps and use its agent themselves."""

import sys

import pytest

from assistant.core import login_session
from assistant.core.mcp import pages, ssh_agent
from assistant.core.mcp.servers import McpServer
from assistant.core.mcp.user import with_user


@pytest.fixture
def from_boot(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv(login_session.FROM_BOOT_ENV, "1")


def test_a_plugin_that_asks_for_the_session_gets_the_helpers_socket_from_boot(from_boot):
    phone = McpServer(name="phone", command="phone-mcp", login_session=True)
    assert with_user(phone).env[login_session.ENV] == str(login_session.socket_path())
    assert login_session.ENV not in with_user(McpServer(name="notes", command="notes-mcp")).env
    page = McpServer(name="phone", page_command="phone-web", login_session=True)
    assert pages._spec(page).env[login_session.ENV] == str(login_session.socket_path())


def test_in_the_session_a_plugin_opens_apps_itself(monkeypatch):
    monkeypatch.delenv(login_session.FROM_BOOT_ENV, raising=False)
    phone = McpServer(name="phone", command="phone-mcp", login_session=True)
    assert login_session.ENV not in with_user(phone).env


def test_from_boot_the_ssh_agent_is_the_sessions_through_the_helpers_link(from_boot, monkeypatch):
    monkeypatch.setenv(ssh_agent.ENV, "/tmp/daemon-agent.sock")
    hosts = McpServer(name="hosts", command="hosts-mcp", ssh_agent=True)
    assert with_user(hosts).env[ssh_agent.ENV] == str(login_session.ssh_agent_link())
    monkeypatch.delenv(login_session.FROM_BOOT_ENV)
    assert with_user(hosts).env[ssh_agent.ENV] == "/tmp/daemon-agent.sock"


def test_only_macos_has_a_login_session_to_reach(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv(login_session.FROM_BOOT_ENV, "1")
    assert not login_session.from_boot()


def test_login_session_is_true_or_false():
    assert login_session.parse(True) and not login_session.parse(None)
    with pytest.raises(ValueError, match="must be true or false"):
        login_session.parse("yes")
