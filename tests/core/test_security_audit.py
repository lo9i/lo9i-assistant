"""The security audit (core/security_audit/): each part from what it reads, and the daemon's whole audit."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lo9i.core import devices
from lo9i.core.mcp.servers import McpServer
from lo9i.core.repositories.known import EXTRAS
from lo9i.core.security_audit import access, local
from lo9i.core.security_audit import service as state

_NOW = datetime(2026, 11, 25, tzinfo=UTC)


def test_a_file_behind_a_closed_folder_is_nobody_elses(tmp_path: Path):
    folder = tmp_path / "home"
    folder.mkdir(mode=0o700)
    (open_file := folder / "lo9i.db").write_text("x")
    open_file.chmod(0o644)
    assert access.readers(open_file) == []
    assert access.readers(folder / "missing") == []


def test_https_is_off_bound_to_one_address_or_open_on_every_interface():
    assert local.https(0, "0.0.0.0", [], []).status == "ok"
    assert local.https(8443, "100.64.0.1", ["lo9i.ts.net"], []).status == "ok"
    wide = local.https(8443, "0.0.0.0", ["lo9i.local"], ["192.168.0.33"])
    assert wide.status == "warn" and "192.168.0.33" in wide.detail and "8443, 8444" in wide.detail
    assert "HTTPS_BIND" in wide.fix


def test_the_local_ports_are_only_on_localhost():
    check = local.local_ports(8765)
    assert check.status == "ok" and "127.0.0.1:8765" in check.detail and ":8766" in check.detail


@pytest.mark.parametrize(("readers", "status"), [([], "ok"), (["group"], "warn"), (["group", "everyone"], "fail")])
def test_a_private_file_fails_when_everyone_reads_it_and_warns_for_the_group(tmp_path, monkeypatch, readers, status):
    path = tmp_path / "secrets.key"
    path.write_text("k")
    monkeypatch.setattr(access, "readers", lambda _: readers)
    check = local.private_file("permissions:secrets", "Secret key", [path, tmp_path / "missing"])
    assert check is not None and check.status == status
    assert (check.fix == f"chmod 600 {path}") == bool(readers)


def test_a_private_file_not_there_is_left_out(tmp_path):
    assert local.private_file("permissions:env", ".env", [tmp_path / ".env"]) is None


def test_the_socket_fails_when_others_can_connect(tmp_path, monkeypatch):
    sock = tmp_path / "daemon.sock"
    assert local.socket(sock).status == "ok"
    sock.write_text("")
    monkeypatch.setattr(access, "writers", lambda _: ["everyone"])
    assert local.socket(sock).status == "fail"
    monkeypatch.setattr(access, "writers", lambda _: [])
    assert local.socket(sock).status == "ok"


def test_bash_without_approval_warns():
    assert local.bash_guard("never", ["terminal"]).status == "warn"
    assert local.bash_guard("dangerous", ["terminal"]).status == "ok"
    assert local.bash_guard("always", ["terminal"]).status == "ok"
    assert local.bash_guard("never", ["memory"]).detail == "Off: the agent has no bash."


@pytest.mark.parametrize(("days", "status"), [(2, "ok"), (40, "warn"), (100, "ok")])
def test_a_device_unused_for_a_month_warns_and_one_expired_is_noted(days, status):
    used = (_NOW - timedelta(days=days)).isoformat()
    check = state.device(devices.Device("d1", "Phone", "2026-01-02T00:00:00+00:00", used, "100.1.2.3"), _NOW)
    assert check.id == "device:d1" and check.status == status
    assert ("Expired" in check.detail) == (days >= 90)


def test_the_setup_code_warns_only_while_open_and_reachable():
    assert state.setup_code(False, True) is None
    closed_off, reachable = state.setup_code(True, False), state.setup_code(True, True)
    assert closed_off is not None and closed_off.status == "ok"
    assert reachable is not None and reachable.status == "warn"


def test_plugins_that_run_here_say_what_and_from_where():
    official = McpServer("calendar", command="/usr/bin/uv", source=EXTRAS, trusted=True)
    by_hand = McpServer("mine", command="node", page_command="python")
    unofficial = McpServer("x", command="uv", source="https://example.com/repo", ssh_agent=True)
    assert state.plugin(official).status == "ok" and "trusted" in state.plugin(official).detail
    assert state.plugin(by_hand).status == "warn" and "node, python" in state.plugin(by_hand).detail
    assert state.plugin(unofficial).status == "ok" and "ssh agent" in state.plugin(unofficial).detail
    assert state.plugin(McpServer("x", command="uv", source="https://e.com/r", trusted=True)).status == "warn"
    assert not state.runs_here(McpServer("remote", url="https://mcp.example.com"))
    assert not state.runs_here(McpServer("off", command="uv", enabled=False))


async def test_the_daemon_audits_devices_and_plugins_besides_the_local_parts(service):
    store = service._storage.store
    await devices.add(store, "Laptop", "100.1.2.3", datetime.now(UTC))
    report = await service.security_audit()
    ids = [c.id for c in report.checks]
    assert {"network:local", "network:https", "socket", "bash"} <= set(ids)
    assert any(i.startswith("device:") for i in ids) and "setup_code" not in ids
