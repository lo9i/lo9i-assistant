import os
import pwd
import shutil
from pathlib import Path

import pytest

import assistant.core.tools.bash as bash_module
from assistant.core.config import settings


async def test_commands_run_in_the_workspace_with_the_users_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "not-home"))
    output, artifact = await bash_module._run('pwd; printf "%s" "$HOME"')
    workspace, home = output.splitlines()[1:]
    assert artifact == {"exit_code": 0}
    assert Path(workspace) == Path(settings.workspace_dir).resolve()
    assert home == pwd.getpwuid(os.getuid()).pw_dir


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
async def test_git_signs_in_to_github_through_gh_when_its_installed(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/bin/sh\n")
    (bin_dir / "gh").chmod(0o755)
    monkeypatch.setattr(bash_module, "_SAFE_PATH", f"{bin_dir}:{bash_module._SAFE_PATH}")
    monkeypatch.setattr(bash_module, "_home", lambda: str(tmp_path))
    output, _ = await bash_module._run(
        "GIT_CONFIG_NOSYSTEM=1 git config --get-all credential.https://github.com.helper"
    )
    assert output.splitlines()[1:] == [f"!{bin_dir}/gh auth git-credential"]


def test_no_github_helper_without_gh(monkeypatch, tmp_path):
    monkeypatch.setattr(bash_module, "_SAFE_PATH", str(tmp_path))
    assert not any(key.startswith("GIT_CONFIG") for key in bash_module._environment())
