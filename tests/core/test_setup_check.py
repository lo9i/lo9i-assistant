"""The setup check (core/setup_check/): what each part says, ok, a warning or failing with its fix, from what it reads;
the model's key checked with one cheap request (core/llm/key_check.py); the command's own checks over the daemon's."""

from collections import namedtuple
from pathlib import Path

import httpx
import pytest

from lo9i.core.health import FAILING_AFTER, Health
from lo9i.core.llm import key_check
from lo9i.core.llm.choice import ModelChoice
from lo9i.core.llm.key_check import KeyVerdict
from lo9i.core.setup_check import SetupCheck, local, merged, service

_Usage = namedtuple("_Usage", "total used free")
_GB = 1024**3


def test_the_web_app_is_built_when_its_page_is_there(tmp_path: Path):
    assert local.web_app(tmp_path).status == "fail" and "install.sh" in local.web_app(tmp_path).fix
    (tmp_path / "index.html").write_text("<html>")
    assert local.web_app(tmp_path).status == "ok"


@pytest.mark.parametrize(("free", "status"), [(20 * _GB, "ok"), (3 * _GB, "warn"), (_GB // 2, "fail")])
def test_disk_space_warns_when_low_and_fails_when_nearly_full(tmp_path, monkeypatch, free, status):
    monkeypatch.setattr(local.shutil, "disk_usage", lambda _: _Usage(100 * _GB, 100 * _GB - free, free))
    check = local.disk(tmp_path / "not-there-yet")
    assert check.status == status and check.detail.endswith("of 100 GB.")
    assert bool(check.fix) == (status != "ok")


def test_the_command_is_found_on_path_or_by_the_link_install_sh_makes(tmp_path, monkeypatch):
    link = tmp_path / "bin" / "lo9i"
    monkeypatch.setattr(local, "COMMAND_LINK", link)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert local.command(str(elsewhere)).status == "warn"
    link.parent.mkdir()
    target = tmp_path / "lo9i"
    target.write_text("#!/bin/sh\n")
    target.chmod(0o755)
    link.symlink_to(target)
    assert local.command(str(link.parent)).status == "ok"
    # Linked, but the shell's PATH doesn't have the folder: a new terminal, or a line in its profile.
    away = local.command(str(elsewhere))
    assert away.status == "warn" and "isn't on this shell's PATH" in away.detail
    # The daemon's PATH is a service manager's: the link is enough.
    monkeypatch.setenv("PATH", str(elsewhere))
    assert local.command().status == "ok"
    target.unlink()
    assert local.command(str(elsewhere)).status == "fail"


def test_the_daemon_answering_or_not():
    socket = Path("/tmp/daemon.sock")
    assert local.daemon(True, socket).status == "ok"
    down = local.daemon(False, socket)
    assert down.status == "fail" and down.fix.startswith("Run lo9i")
    assert local.older_daemon(socket).status == "warn"


def test_the_model_needs_a_provider_its_fields_and_a_key_that_works():
    assert service.model("", "", "", None).status == "fail"
    assert service.model("Anthropic", "m", "API key", None).detail == "API key isn't set."
    assert service.model("Anthropic", "", "", None).detail == "No model is set."
    assert service.model("Anthropic", "m", "", KeyVerdict("works")).status == "ok"
    refused = service.model("Anthropic", "m", "", KeyVerdict("refused", "HTTP 401"))
    assert refused.status == "fail" and refused.detail == "Anthropic refused the key: HTTP 401"
    assert service.model("Anthropic", "m", "", KeyVerdict("unreachable", "timed out")).status == "warn"
    assert service.model("Groq", "m", "", KeyVerdict("unchecked")).status == "ok"


def test_a_plugin_from_its_connection_and_its_failures_in_a_row():
    assert service.plugin("calendar", "connected", "", 4, Health()).detail == "Connected, 4 tools."
    assert service.plugin("calendar", "idle", "", 4, Health()).status == "ok"
    assert service.plugin("calendar", "failed", "exit 1", 0, Health()).detail == "Doesn't start: exit 1"
    assert service.plugin("calendar", "idle", "", 4, Health(failures=1, error="boom")).status == "warn"
    assert service.plugin("calendar", "idle", "", 4, Health(failures=FAILING_AFTER, error="boom")).status == "fail"
    lost = service.plugin("notion", "needs_sign_in", "", 0, Health(signed_out=True, error="refused"))
    assert lost.status == "fail" and "Sign in again" in lost.fix
    assert service.plugin("calendar", "off", "", 0, Health()).status == "warn"


def test_email_accounts_and_chat_channels_from_their_state():
    assert service.email("a1", "Work", "ok", "").status == "ok"
    assert (
        service.email("a1", "Work", "needs_sign_in", "The password was refused.").detail == "The password was refused."
    )
    assert service.channel("telegram", True, "").status == "ok"
    assert service.channel("telegram", False, "").status == "fail"
    assert service.channel("slack", False, "Update it.").detail == "Update it."


def test_the_commands_own_checks_go_over_the_daemons():
    daemon = [SetupCheck("daemon", "Daemon", "ok", "a"), SetupCheck("command", "lo9i command", "ok", "linked")]
    own = [SetupCheck("command", "lo9i command", "warn", "not on PATH")]
    assert [c.detail for c in merged(daemon, own)] == ["a", "not on PATH"]


def _choice(provider: str, **values: str) -> ModelChoice:
    return ModelChoice(provider, "m", "w", {"api_key": "k", **values})


async def test_the_key_is_checked_with_one_request_that_calls_no_model():
    asked: list[str] = []

    def answer(status: int):
        def handler(request: httpx.Request) -> httpx.Response:
            asked.append(str(request.url))
            return httpx.Response(status, json={})

        return httpx.MockTransport(handler)

    assert await key_check.check(_choice("anthropic"), answer(401)) == KeyVerdict("refused", "HTTP 401")
    assert await key_check.check(_choice("openrouter"), answer(200)) == KeyVerdict("works")
    ollama = _choice("openai", base_url="http://localhost:11434/v1/")
    assert await key_check.check(ollama, answer(404)) == KeyVerdict("unchecked")
    assert await key_check.check(_choice("openai"), answer(500)) == KeyVerdict("unreachable", "HTTP 500")
    assert asked == [
        "https://api.anthropic.com/v1/models?limit=1",
        "https://openrouter.ai/api/v1/key",
        "http://localhost:11434/v1/models",
        "https://api.openai.com/v1/models",
    ]
    assert await key_check.check(_choice("groq")) == KeyVerdict("unchecked")


async def test_a_provider_out_of_reach_is_told_apart_from_a_refused_key():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    verdict = await key_check.check(_choice("openrouter"), httpx.MockTransport(down))
    assert verdict == KeyVerdict("unreachable", "connection refused")
