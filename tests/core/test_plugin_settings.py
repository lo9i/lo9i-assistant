"""An installed plugin's settings (core/mcp/plugin_settings.py, core/agent/plugin_settings.py): its fields read with
their values, a secret one only as set, and changed after it's installed, its check running before anything is
saved; and the MCP page's env change, which keeps what a plugin's server.yaml sets."""

import pytest

from assistant.core.agent import McpServer, McpServerChanges, McpServerError, ServerValues
from assistant.core.mcp import keys, plugin_settings, servers
from assistant.core.mcp.checks import CheckFailedError
from assistant.core.mcp.install import ServerField
from tests.core.test_repositories import URL, _write, repo  # noqa: F401 (a fixture)

# The check refuses any token but "good", and a region it doesn't know.
_CHECK = """
import os, sys
if os.environ.get("GREET_TOKEN") != "good" or os.environ.get("GREET_REGION") == "mars":
    print("The service refused the token.")
    sys.exit(1)
"""

_MANIFEST = """
description: Greets
command: "{python}"
args: ["{dir}/server.py"]
env: {GREET_HOST: "https://greet.example"}
check:
  command: "{python}"
  args: ["{dir}/check.py"]
fields:
  - {key: GREET_TOKEN, label: Token, secret: true}
  - {key: GREET_REGION, label: Region, optional: true}
  - {key: GREET_PIN, label: PIN, secret: true, optional: true}
"""


@pytest.fixture
async def greet(service, repo):  # noqa: F811 (the fixture imported above)
    _write(repo / "other" / "general" / "greet", {"server.yaml": _MANIFEST, "server.py": "", "check.py": _CHECK})
    values = {"GREET_TOKEN": "good", "GREET_REGION": "eu", "GREET_PIN": "1234"}
    await service.install_from_repository(URL, [], [ServerValues("greet", values)])


async def _saved(service) -> dict[str, str]:
    """The env its processes get."""
    return (await keys.fill(service.store, service.secrets, await servers.load(service.store, "greet"))).env


async def test_its_fields_show_their_values_and_a_secret_only_as_set(service, greet):
    shown = await service.plugin_settings("greet")
    assert shown.check
    assert [(f.key, f.value, f.set, f.secret) for f in shown.fields] == [
        ("GREET_TOKEN", "", True, True),
        ("GREET_REGION", "eu", True, False),
        ("GREET_PIN", "", True, True),
    ]
    assert "good" not in str(shown) and "1234" not in str(shown)
    # Its status says it has settings; a server added by hand has none.
    await service.add_mcp_server(McpServer("notes", command="notes-mcp", env={"KEY": "1"}))
    assert {s.name: s.settings for s in await service.mcp_servers()} == {"greet": True, "notes": False}


async def test_a_new_value_is_saved_and_the_rest_stays(service, greet):
    await service.change_plugin_settings("greet", {"GREET_REGION": "us", "GREET_TOKEN": ""}, [])
    env = await _saved(service)
    # The empty secret kept its saved value, the PIN not given kept its own, and what server.yaml sets stays.
    assert env == {
        "GREET_HOST": "https://greet.example",
        "GREET_TOKEN": "good",
        "GREET_REGION": "us",
        "GREET_PIN": "1234",
    }


async def test_values_its_check_refuses_are_not_saved(service, greet):
    with pytest.raises(CheckFailedError, match=r"^greet: The service refused the token\.$"):
        await service.change_plugin_settings("greet", {"GREET_TOKEN": "bad", "GREET_REGION": "us"}, [])
    # A field not secret is checked with its new value, the token left empty with the saved one.
    with pytest.raises(CheckFailedError):
        await service.change_plugin_settings("greet", {"GREET_TOKEN": "", "GREET_REGION": "mars"}, [])
    assert (await _saved(service))["GREET_REGION"] == "eu"


async def test_an_optional_field_is_emptied_and_a_secret_only_when_cleared(service, greet):
    shown = await service.change_plugin_settings("greet", {"GREET_REGION": "", "GREET_PIN": ""}, [])
    assert (await _saved(service))["GREET_PIN"] == "1234"
    shown = await service.change_plugin_settings("greet", {}, ["GREET_PIN"])
    env = await _saved(service)
    assert (env["GREET_REGION"], env["GREET_PIN"], env["GREET_TOKEN"]) == ("", "", "good")
    assert [(f.key, f.set) for f in shown.fields] == [
        ("GREET_TOKEN", True),
        ("GREET_REGION", False),
        ("GREET_PIN", False),
    ]


async def test_a_required_field_unknown_field_or_server_added_by_hand_is_refused(service, greet):
    with pytest.raises(McpServerError, match="needs Token"):
        await service.change_plugin_settings("greet", {}, ["GREET_TOKEN"])
    with pytest.raises(McpServerError, match="no setting GREET_HOST"):
        await service.change_plugin_settings("greet", {"GREET_HOST": "https://elsewhere"}, [])
    await service.add_mcp_server(McpServer("notes", command="notes-mcp", env={"KEY": "1"}))
    with pytest.raises(McpServerError, match="added by hand"):
        await service.plugin_settings("notes")


async def test_the_mcp_pages_env_change_keeps_what_a_plugins_server_yaml_sets(service, greet):
    await service.update_mcp_server("greet", McpServerChanges(env={"GREET_REGION": "us"}))
    env = await _saved(service)
    assert (env["GREET_HOST"], env["GREET_REGION"], env["GREET_TOKEN"]) == ("https://greet.example", "us", "good")
    # A server added by hand has nothing set for it: what's typed replaces its env.
    await service.add_mcp_server(McpServer("notes", command="notes-mcp", env={"A": "1", "B": "2"}))
    await service.update_mcp_server("notes", McpServerChanges(env={"B": "3"}))
    assert (await servers.load(service.store, "notes")).env == {"B": ""}


def test_changed_goes_into_the_headers_of_a_remote_plugin():
    server = McpServer("remote", url="https://x", headers={"X-Org": "lo9i", "Authorization": "old"}, source=URL)
    fields = [ServerField("Authorization", "Token", secret=True)]
    change = plugin_settings.changed(server, fields, {"Authorization": "new"}, [])
    assert change.server.headers == {"X-Org": "lo9i", "Authorization": "new"} and change.cleared == frozenset()
