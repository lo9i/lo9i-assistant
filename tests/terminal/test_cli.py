"""The `lo9i` command: its arguments, the completion scripts written from them, and `lo9i doctor` while the daemon is
down."""

import json
import shutil
import subprocess

import pytest

from lo9i_terminal import setup_check_command
from lo9i_terminal.cli import Command, parse
from lo9i_terminal.completion import script


def test_the_commands_parse():
    assert parse([]) == Command("chat")
    assert parse(["daemon"]) == Command("daemon")
    assert parse(["daemon", "restart"]) == Command("daemon", "restart")
    assert parse(["doctor", "--json"]) == Command("doctor", json=True)
    assert parse(["completion", "fish"]) == Command("completion", "fish")


@pytest.mark.parametrize("args", [["--help"], ["--version"], ["completion", "tcsh"], ["nope"]])
def test_help_version_and_mistakes_exit_as_argparse_does(args, capsys):
    with pytest.raises(SystemExit) as ended:
        parse(args)
    assert ended.value.code == (0 if args[0].startswith("--") else 2)
    out = capsys.readouterr()
    if args == ["--version"]:
        assert out.out.startswith("lo9i 0.")
    if args == ["--help"]:
        assert "doctor" in out.out and "completion" in out.out


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_each_completion_script_offers_the_commands_and_is_valid(shell, tmp_path):
    text = script(shell)
    assert all(word in text for word in ("daemon", "doctor", "completion", "restart", "json"))
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} isn't installed")
    path = tmp_path / f"lo9i.{shell}"
    path.write_text(text)
    assert subprocess.run([shell, "-n", str(path)], capture_output=True).returncode == 0


async def test_doctor_checks_what_it_can_while_the_daemon_is_down(capsys):
    assert await setup_check_command.doctor(as_json=True) == 1
    checks = {c["id"]: c for c in json.loads(capsys.readouterr().out)["checks"]}
    assert list(checks) == ["daemon", "web_app", "disk", "command"]
    assert checks["daemon"]["status"] == "fail" and checks["daemon"]["detail"].startswith("Not answering on ")
