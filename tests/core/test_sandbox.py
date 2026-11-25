"""The bash sandbox (core/sandbox/) against a fake `docker`: it records its arguments and runs the command it's given
on this computer, which is enough to check what the container would get and how failures read."""

import json
from pathlib import Path

import pytest

import lo9i.core.tools.bash as bash_module
from lo9i.core.agent import SandboxUnavailableError
from lo9i.core.config import settings
from lo9i.core.sandbox import runtime as runtimes
from lo9i.core.sandbox import setting
from lo9i.core.setup_check import service as setup_checks

_FAKE = """#!/bin/bash
printf '%s\\n' "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "$@")" >> "{log}"
case "$1" in
  info) exit {info} ;;
  pull) exit 0 ;;
  rm) exit 0 ;;
  run) [ -n "{exit_run}" ] && {{ echo "docker: error during connect"; exit {exit_run}; }}; exec bash -c "${{@: -1}}" ;;
esac
"""


@pytest.fixture
def docker(tmp_path, monkeypatch):
    """A fake docker on the runtimes' path; `docker(info=1, run=125)` changes how it answers."""
    log = tmp_path / "docker.log"

    def install(info: int = 0, run: int | None = None) -> Path:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        fake = bin_dir / "docker"
        fake.write_text(_FAKE.format(log=log, info=info, exit_run="" if run is None else run))
        fake.chmod(0o755)
        monkeypatch.setattr(runtimes, "_SEARCHED", f"{bin_dir}:/usr/bin:/bin")
        return log

    return install


def _calls(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text().splitlines()]


async def test_a_command_runs_in_a_container_with_only_the_workspace(docker):
    log = docker()
    output, artifact = await bash_module._in_sandbox("echo hi")
    assert (output, artifact) == ("exit code: 0\nhi\n", {"exit_code": 0})
    run = _calls(log)[0]
    workspace = Path(settings.workspace_dir).resolve()
    assert run[0] == "run" and run[-4:] == [settings.bash_sandbox_image, "bash", "-c", "echo hi"]
    mounts = [run[i + 1] for i, arg in enumerate(run) if arg == "--volume"]
    assert mounts == [f"{workspace}:/workspace"]
    assert "--cap-drop" in run and "--rm" in run


async def test_without_a_runtime_the_command_doesnt_run_and_says_why(monkeypatch, tmp_path):
    monkeypatch.setattr(runtimes, "_SEARCHED", str(tmp_path))
    output, artifact = await bash_module._in_sandbox("touch ran")
    assert artifact is None
    assert "neither Docker nor Podman is installed" in output and "didn't run" in output
    assert not (Path(settings.workspace_dir) / "ran").exists()


async def test_a_runtime_not_running_is_said_plainly(docker):
    docker(info=1, run=125)
    output, artifact = await bash_module._in_sandbox("echo hi")
    assert artifact is None
    assert output.startswith("The sandbox is on, but Docker isn't running, so the command didn't run.")


async def test_a_failure_says_what_the_sandbox_leaves_out(docker):
    docker()
    output, artifact = await bash_module._in_sandbox("exit 3")
    assert artifact == {"exit_code": 3}
    assert "only the workspace is there" in output and "lo9i's data" in output


async def test_a_command_that_times_out_has_its_container_removed(docker, monkeypatch):
    log = docker()
    monkeypatch.setattr(settings, "bash_timeout", 1)
    output, artifact = await bash_module._in_sandbox("sleep 5")
    assert artifact == {"exit_code": None} and output.startswith("Timed out")
    run, removed = _calls(log)
    assert removed == ["rm", "--force", run[run.index("--name") + 1]]


async def test_a_workspace_holding_the_data_folder_isnt_mounted(docker, monkeypatch):
    log = docker()
    monkeypatch.setattr(settings, "workspace_dir", str(Path(settings.database_path).parent))
    output, artifact = await bash_module._in_sandbox("echo hi")
    assert artifact is None and "holds lo9i's data folder" in output
    assert not log.exists()


async def test_it_cant_be_turned_on_without_a_runtime_that_answers(service, docker):
    docker(info=1)
    with pytest.raises(SandboxUnavailableError, match="isn't running"):
        await service.set_sandbox(True)
    assert not await setting.enabled(service._storage.store)


async def test_turning_it_on_downloads_the_image_first(service, docker):
    log = docker()
    status = await service.set_sandbox(True)
    assert status.enabled and status.available and status.runtime == "docker"
    assert ["pull", settings.bash_sandbox_image] in _calls(log)


def test_the_setup_check_fails_when_its_on_without_a_runtime():
    check = setup_checks.sandbox(True, "", "Neither Docker nor Podman is installed.", "Install one.")
    assert (check.status, check.fix) == ("fail", "Install one.")
    assert setup_checks.sandbox(False, "", "Neither is installed.", "Install one.").detail.startswith("Off, and it")
