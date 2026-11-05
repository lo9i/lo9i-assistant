"""install.sh: its options, a dry run that changes nothing, and putting the lo9i command on PATH with its completion,
once however often it runs. Each runs bash with a home folder of the test's."""

import os
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parents[2] / "install.sh"


def _bash(
    home: Path, command: str, shell: str = "/bin/zsh", path: str = "/usr/bin:/bin"
) -> subprocess.CompletedProcess:
    env = {"HOME": str(home), "SHELL": shell, "PATH": path, "TMPDIR": os.environ.get("TMPDIR", "/tmp")}
    return subprocess.run(["bash", "-c", command], env=env, capture_output=True, text=True, timeout=60)


def test_help_and_an_unknown_option(tmp_path):
    shown = _bash(tmp_path, f"bash {_SCRIPT} --help")
    assert shown.returncode == 0 and "--dry-run" in shown.stdout and "--skip-shell" in shown.stdout
    # Piped, as `curl ... | bash -s -- --help`.
    piped = _bash(tmp_path, f"bash -s -- --help < {_SCRIPT}")
    assert piped.returncode == 0 and "--no-completion" in piped.stdout
    wrong = _bash(tmp_path, f"bash {_SCRIPT} --nope")
    assert wrong.returncode == 2 and "Unknown option: --nope" in wrong.stderr


def test_a_dry_run_says_what_it_would_do_and_changes_nothing(tmp_path):
    # uv and git stay findable; ~/.local/bin isn't on PATH, so it would add it.
    path = os.environ["PATH"]
    ran = _bash(tmp_path, f"bash {_SCRIPT} --dry-run", path=path)
    assert ran.returncode == 0, ran.stderr
    assert "Would link" in ran.stderr and "Would write the zsh completion" in ran.stderr
    assert "Dry run: nothing was changed." in ran.stderr
    assert list(tmp_path.iterdir()) == []


def _installs(root: Path, options: str = "") -> str:
    """The shell part alone, sourced, for a checkout whose command prints what it's asked."""
    return f"source {_SCRIPT}; parse_args {options}; ROOT={root}; install_command"


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    command = tmp_path / "checkout" / ".venv" / "bin" / "lo9i"
    command.parent.mkdir(parents=True)
    command.write_text('#!/bin/sh\necho "completion for $2"\n')
    command.chmod(0o755)
    return tmp_path / "checkout"


def test_the_command_is_linked_onto_path_with_its_completion_once(tmp_path, checkout):
    home = tmp_path / "home"
    home.mkdir()
    for _ in range(2):
        assert _bash(home, _installs(checkout)).returncode == 0
    assert (home / ".local/bin/lo9i").resolve() == checkout / ".venv/bin/lo9i"
    assert (home / ".local/share/zsh/site-functions/_lo9i").read_text() == "completion for zsh\n"
    profile = (home / ".zshrc").read_text()
    assert profile.count(f'export PATH="{home}/.local/bin:$PATH"') == 1
    assert profile.count("(( $+functions[compdef] )) && source") == 1


def test_fish_gets_its_completion_folder_and_path(tmp_path, checkout):
    home = tmp_path / "home"
    home.mkdir()
    assert _bash(home, _installs(checkout), shell="/usr/bin/fish").returncode == 0
    assert (home / ".config/fish/completions/lo9i.fish").read_text() == "completion for fish\n"
    assert f'fish_add_path -g "{home}/.local/bin"' in (home / ".config/fish/config.fish").read_text()


def test_the_options_leave_out_the_path_the_completion_or_the_profiles(tmp_path, checkout):
    home = tmp_path / "home"
    home.mkdir()
    assert _bash(home, _installs(checkout, "--skip-shell --no-completion")).returncode == 0
    assert (home / ".local/bin/lo9i").is_symlink() and not (home / ".zshrc").exists()
    assert not (home / ".local/share").exists()
    assert _bash(home, _installs(checkout, "--no-path"), shell="/bin/bash").returncode == 0
    assert (home / ".local/share/bash-completion/completions/lo9i").is_file()
    bash_profile = next(p for p in (home / ".bash_profile", home / ".bashrc") if p.exists()).read_text()
    assert "export PATH" not in bash_profile and "completions/lo9i" in bash_profile


def test_a_lo9i_that_isnt_a_link_is_left_alone(tmp_path, checkout):
    home = tmp_path / "home"
    (home / ".local/bin").mkdir(parents=True)
    (home / ".local/bin/lo9i").write_text("someone else's")
    ran = _bash(home, _installs(checkout, "--no-completion"))
    assert ran.returncode == 0 and "isn't a link; leaving it" in ran.stderr
    assert (home / ".local/bin/lo9i").read_text() == "someone else's"
