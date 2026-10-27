"""Updating lo9i from the apps: a clone fetches its upstream branch, and an update fast-forwards to it, runs the
install steps and restarts. The repositories here are real, made in a temporary folder."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest

from assistant.daemon import updates
from assistant.daemon.updates import VERSION_FILE, Step, Updates
from assistant.protocol import Commit, UpdateError, UpdateStatus
from tests.conftest import written


def _git(folder: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=folder, check=True, capture_output=True, text=True).stdout


def _commit(folder: Path, name: str, subject: str) -> None:
    (folder / name).write_text(subject)
    _git(folder, "add", name)
    _git(folder, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", subject)


@pytest.fixture
def repos(tmp_path) -> tuple[Path, Path]:
    """The repository everyone pushes to, and lo9i's clone of it; and a second clone to push from."""
    origin, clone, other = tmp_path / "origin.git", tmp_path / "lo9i", tmp_path / "other"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(other))
    _commit(other, "a.txt", "First")
    _git(other, "push", "-q", "origin", "HEAD:main")
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    return clone, other


class _Spy:
    def __init__(self) -> None:
        self.restarts = 0
        self.announced = 0

    def restart(self) -> int:
        self.restarts += 1
        return 0

    def announce(self) -> None:
        self.announced += 1


class _Runs:
    """Records when runs were held off and let through again, with the commit the clone was at."""

    def __init__(self, clone: Path) -> None:
        self.clone = clone
        self.done: list[tuple[str, str]] = []

    async def hold_runs(self, reason: str) -> None:
        self.done.append(("held", _git(self.clone, "log", "-1", "--format=%s").strip()))

    def release_runs(self) -> None:
        self.done.append(("released", _git(self.clone, "log", "-1", "--format=%s").strip()))


def _updates(clone: Path, spy: _Spy, steps: list[Step] | None = None, runs: _Runs | None = None) -> Updates:
    return Updates(clone, steps or [], spy.restart, spy.announce, runs)


async def _until_done(lo9i: Updates) -> None:
    async with asyncio.timeout(30):
        while (await lo9i.status()).state == "updating":
            await asyncio.sleep(0.05)


async def test_a_clone_says_which_commit_it_runs_and_is_up_to_date_after_a_check(repos):
    clone, _ = repos
    lo9i = _updates(clone, _Spy())
    status = await lo9i.status()
    assert status.installed_from == "git" and status.current and status.current.subject == "First"
    assert (status.checked_at, status.can_update) == ("", False)
    checked = await lo9i.check()
    assert (checked.upstream, checked.behind, checked.new, checked.reason) == ("origin/main", 0, [], "")
    assert checked.can_update


async def test_a_check_lists_the_new_commits_newest_first(repos):
    clone, other = repos
    _commit(other, "b.txt", "Second")
    _commit(other, "c.txt", "Third")
    _git(other, "push", "-q", "origin", "HEAD:main")
    checked = await _updates(clone, _Spy()).check()
    assert checked.behind == 2 and [c.subject for c in checked.new] == ["Third", "Second"]


async def test_an_update_fast_forwards_runs_the_steps_and_restarts(repos, tmp_path):
    clone, other = repos
    _commit(other, "b.txt", "Second")
    _git(other, "push", "-q", "origin", "HEAD:main")
    spy, marker = _Spy(), tmp_path / "synced"
    lo9i = _updates(clone, spy, [Step("Installing its dependencies", ["touch", str(marker)])])
    started = await lo9i.start()
    assert started.state == "updating"
    await _until_done(lo9i)
    status = await lo9i.status()
    assert (status.state, status.current and status.current.subject) == ("restarting", "Second")
    assert (clone / "b.txt").exists() and marker.exists()
    assert spy.restarts == 1 and spy.announced >= 3


async def test_a_step_that_fails_says_which_and_why_and_nothing_restarts(repos):
    clone, other = repos
    _commit(other, "b.txt", "Second")
    _git(other, "push", "-q", "origin", "HEAD:main")
    spy = _Spy()
    steps = [Step("Building the web app", ["sh", "-c", "echo 'npm ERR! missing script: build' >&2; exit 1"])]
    lo9i = _updates(clone, spy, steps)
    await lo9i.start()
    await _until_done(lo9i)
    status = await lo9i.status()
    assert status.state == "failed" and spy.restarts == 0
    assert status.error.startswith("Building the web app failed: npm ERR! missing script: build. ")


async def test_a_step_that_fails_after_the_new_commits_came_goes_back_to_the_version_before(repos, tmp_path):
    clone, other = repos
    _commit(other, "b.txt", "Second")
    _git(other, "push", "-q", "origin", "HEAD:main")
    installed = tmp_path / "installed"
    steps = [
        Step("Installing its dependencies", ["sh", "-c", f"git log -1 --format=%s >> {installed}"]),
        # Fails on the new version, after changing a file the repository has.
        Step("Building the web app", ["sh", "-c", "test ! -f b.txt || { echo half > a.txt; exit 1; }"]),
        Step("Never run", ["sh", "-c", f"echo never >> {installed}"]),
    ]
    spy = _Spy()
    lo9i = _updates(clone, spy, steps)
    await lo9i.start()
    await _until_done(lo9i)
    status = await lo9i.status()
    assert (status.state, status.current and status.current.subject) == ("failed", "First") and spy.restarts == 0
    assert status.error.endswith("lo9i went back to the version it was on, which keeps running.")
    assert installed.read_text().split() == ["Second", "First"]  # what the old version needs, installed again
    assert not (clone / "b.txt").exists() and (clone / "a.txt").read_text() == "First"


async def test_going_back_that_fails_too_says_a_restart_would_run_a_half_installed_version(repos):
    clone, other = repos
    _commit(other, "b.txt", "Second")
    _git(other, "push", "-q", "origin", "HEAD:main")
    lo9i = _updates(clone, _Spy(), [Step("Installing its dependencies", ["sh", "-c", "exit 1"])])
    await lo9i.start()
    await _until_done(lo9i)
    error = (await lo9i.status()).error
    assert "Going back: Installing its dependencies failed too" in error
    assert error.endswith("A restart now would run a version that isn't fully installed.")


async def test_changes_not_committed_or_commits_not_pushed_keep_the_copy_as_it_is(repos):
    clone, other = repos
    _commit(other, "b.txt", "Second")
    _git(other, "push", "-q", "origin", "HEAD:main")
    (clone / "a.txt").write_text("edited here")
    lo9i = _updates(clone, _Spy())
    with pytest.raises(UpdateError, match="changes that aren't committed"):
        await lo9i.start()
    _git(clone, "checkout", "-q", "a.txt")
    _commit(clone, "mine.txt", "Mine")
    with pytest.raises(UpdateError, match="1 commit\\(s\\) origin/main doesn't have"):
        await lo9i.start()
    assert not (clone / "b.txt").exists()


async def test_nothing_new_is_nothing_to_install(repos):
    clone, _ = repos
    with pytest.raises(UpdateError, match="up to date"):
        await _updates(clone, _Spy()).start()


async def test_a_branch_without_upstream_or_an_unreachable_repository_says_so(repos, tmp_path):
    clone, _ = repos
    _git(clone, "checkout", "-q", "-b", "local-only")
    checked = await _updates(clone, _Spy()).check()
    assert not checked.can_update and "follows no branch" in checked.reason
    _git(clone, "checkout", "-q", "main")
    _git(clone, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    checked = await _updates(clone, _Spy()).check()
    assert not checked.can_update and checked.reason.startswith("Couldn't reach the repository:")


async def test_a_deployed_copy_shows_the_commit_it_came_from_and_is_updated_by_deploying(tmp_path):
    copy = tmp_path / "copy"
    copy.mkdir()
    updates.write_version(copy, Commit("abc123", "Ship it", "2026-10-24T00:00:00Z"))
    assert json.loads((copy / VERSION_FILE).read_text())["subject"] == "Ship it"
    lo9i = _updates(copy, _Spy())
    status = await lo9i.check()
    assert status.installed_from == "deployed" and status.current == Commit("abc123", "Ship it", "2026-10-24T00:00:00Z")
    assert not status.can_update and "scripts/deploy.sh" in status.reason
    with pytest.raises(UpdateError, match="Deploy again"):
        await lo9i.start()


async def test_the_version_written_for_a_deploy_says_when_it_has_changes_not_committed(repos):
    clone, _ = repos
    (clone / "a.txt").write_text("edited")
    version = await updates._this_version(clone)
    assert version.subject == "First (with changes not committed)"


def _pushed(other: Path) -> None:
    _commit(other, "b.txt", "Second")
    _git(other, "push", "-q", "origin", "HEAD:main")


async def test_two_updates_asked_for_at_once_install_once_and_a_check_meanwhile_leaves_it_installing(repos, tmp_path):
    clone, other = repos
    _pushed(other)
    ran, release = tmp_path / "ran", tmp_path / "release"
    step = Step(
        "Installing its dependencies", ["sh", "-c", f"echo x >> {ran}; until [ -f {release} ]; do sleep 0.02; done"]
    )
    spy = _Spy()
    lo9i = _updates(clone, spy, [step])
    first, second, checked = await asyncio.gather(lo9i.start(), lo9i.start(), lo9i.check(), return_exceptions=True)
    assert isinstance(first, UpdateStatus) and first.state == "updating"
    assert isinstance(second, UpdateError) and "already being installed" in str(second)
    assert isinstance(checked, UpdateStatus) and checked.state == "updating" and lo9i.installing()
    with pytest.raises(UpdateError, match="already being installed"):
        await lo9i.start()
    release.touch()
    await asyncio.wait_for(lo9i.until_installed(), 30)
    assert ran.read_text().split() == ["x"] and spy.restarts == 1 and not lo9i.installing()


async def test_once_the_daemon_is_ending_no_update_starts(repos):
    clone, other = repos
    _pushed(other)
    lo9i = _updates(clone, _Spy())
    lo9i.close()
    with pytest.raises(UpdateError, match="restarting or stopping"):
        await lo9i.start()
    assert not (clone / "b.txt").exists()
    await asyncio.wait_for(lo9i.until_installed(), 1)


async def test_a_git_command_that_fails_after_the_fetch_says_why_and_the_check_ends(repos, monkeypatch):
    clone, other = repos
    _pushed(other)
    real = updates._git

    async def git(root: Path, *args: str) -> str:
        if args[0] == "status":
            raise updates._FailedError("fatal: index file corrupt")
        return await real(root, *args)

    monkeypatch.setattr(updates, "_git", git)
    checked = await _updates(clone, _Spy()).check()
    assert checked.state == "idle" and not checked.can_update
    assert checked.reason == "Couldn't compare this copy with origin/main: fatal: index file corrupt"


def test_the_web_apps_packages_install_as_the_lock_has_them(monkeypatch, tmp_path):
    monkeypatch.setattr(updates.shutil, "which", lambda name: f"/usr/bin/{name}")
    commands = [step.command for step in updates.default_steps(tmp_path)]
    assert ["/usr/bin/npm", "--prefix", "clients/web", "ci", "--no-audit", "--no-fund", "--silent"] in commands
    assert not any("install" in command for command in commands)


async def test_a_step_whose_update_is_cancelled_is_killed(tmp_path):
    pid = tmp_path / "pid"
    step = asyncio.create_task(updates._run(tmp_path, ["sh", "-c", f"echo $$ > {pid}; exec sleep 30"], 60))
    child = int(await written(pid))
    step.cancel()
    with pytest.raises(asyncio.CancelledError):
        await step
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)


async def test_an_update_cancelled_outright_goes_back_at_the_next_start_and_restarts(repos, tmp_path):
    clone, other = repos
    _commit(other, "b.txt", "Second")
    _git(other, "push", "-q", "origin", "HEAD:main")
    installed, started = tmp_path / "installed", tmp_path / "started"
    steps = [
        Step("Installing its dependencies", ["sh", "-c", f"git log -1 --format=%s >> {installed}"]),
        # Holds the update on the new version until it's cancelled (the daemon crashing).
        Step("Building the web app", ["sh", "-c", f"test ! -f b.txt || {{ echo up > {started}; exec sleep 30; }}"]),
    ]
    first = _updates(clone, _Spy(), steps)
    await first.start()
    await written(started)
    assert first._task is not None
    first._task.cancel()
    await first.until_installed()
    assert (clone / "b.txt").exists()
    spy = _Spy()
    again = _updates(clone, spy, steps)
    await again.recover()
    assert again.installing()
    await again.until_installed()
    status = await again.status()
    assert (status.state, status.current and status.current.subject) == ("restarting", "First") and spy.restarts == 1
    assert installed.read_text().split() == ["Second", "First"]
    # Gone once it's back: the start after that has nothing to do.
    spy_after = _Spy()
    after = _updates(clone, spy_after, steps)
    await after.recover()
    assert not after.installing() and spy_after.restarts == 0


async def test_an_update_that_ended_before_its_new_commits_came_only_forgets_it(repos):
    clone, _ = repos
    head = _git(clone, "rev-parse", "HEAD").strip()
    mark = clone / _git(clone, "rev-parse", "--git-path", "lo9i-update.json").strip()
    mark.write_text(json.dumps({"before": head}))
    spy = _Spy()
    lo9i = _updates(clone, spy)
    await lo9i.recover()
    await lo9i.until_installed()
    assert (await lo9i.status()).state == "idle" and spy.restarts == 0 and not mark.exists()


async def test_runs_are_held_off_before_anything_changes_and_until_the_restart(repos):
    clone, other = repos
    _commit(other, "b.txt", "Second")
    _git(other, "push", "-q", "origin", "HEAD:main")
    runs = _Runs(clone)
    lo9i = _updates(clone, _Spy(), runs=runs)
    await lo9i.start()
    await _until_done(lo9i)
    assert runs.done == [("held", "First")]  # still held: the restart comes next


async def test_an_update_that_fails_lets_the_runs_held_off_go_on(repos):
    clone, other = repos
    _commit(other, "b.txt", "Second")
    _git(other, "push", "-q", "origin", "HEAD:main")
    runs = _Runs(clone)
    lo9i = _updates(clone, _Spy(), [Step("Installing its dependencies", ["sh", "-c", "exit 1"])], runs)
    await lo9i.start()
    await _until_done(lo9i)
    assert runs.done == [("held", "First"), ("released", "First")]
