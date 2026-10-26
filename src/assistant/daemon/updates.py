"""Updating lo9i from the apps (Settings → System, `/host`): which version the daemon runs, whether a newer one
is there, and installing it, then restarting (daemon/shutdown.py).

The version is a commit of lo9i's repository. A clone (install.sh, or a checkout someone works in) updates
itself: it fetches its upstream branch, and an update fast-forwards to it, syncs the dependencies, builds the
web app when npm is there, and restarts once no run is in progress; one that fails after the fast-forward goes
back to the commit it came from and installs what that one needs again. A clone with changes not committed, or
commits its upstream doesn't have, isn't touched: the update says why instead. A copy scripts/deploy.sh made
has no repository; it carries the commit it was made from (`VERSION_FILE`) and is updated by deploying again.

One update at a time, and the daemon never ends in the middle of one: a restart or stop waits for it as it waits
for runs (daemon/shutdown.py), and a signal's stop waits for it too (server.py, `close` and `until_installed`),
so the tree is left either on the new version with what it needs or back on the old one. An update the daemon
ended in the middle of all the same (its task cancelled outright, a crash) leaves a mark in the repository's git
folder (`_MARK`) with the commit it came from, and the next start goes back to it (`recover`).
"""

import asyncio
import json
import logging
import os
import shutil
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from assistant.core import uv
from assistant.protocol import Commit, UpdateError, UpdateStatus

logger = logging.getLogger(__name__)

# Written by scripts/deploy.sh into the copy it makes: the commit it was made from.
VERSION_FILE = ".lo9i-version"
# The most new commits listed.
_LISTED = 30
_GIT_SECONDS = 60
# One line per commit: its sha, subject and date, apart by a character no subject has.
_FORMAT = "--format=%H%x1f%s%x1f%cI"
_NPM_PLACES = ("/opt/homebrew/bin/npm", "/usr/local/bin/npm", "/usr/bin/npm")
_MERGE = "Downloading the update"
# In the repository's git folder while an update is being installed: the commit it came from.
_MARK = "lo9i-update.json"
_UNFINISHED = "The last update didn't finish"


@dataclass(frozen=True)
class Step:
    """A command an update runs in the repository, after it has the new commits."""

    label: str
    command: list[str]
    timeout: float = 900


class _FailedError(Exception):
    pass


@dataclass(frozen=True)
class _Checked:
    upstream: str
    new: list[Commit]
    checked_at: str
    reason: str


class Updates:
    def __init__(
        self, root: Path, steps: Sequence[Step], restart: Callable[[], object], announce: Callable[[], None]
    ) -> None:
        """`steps` install what the new commits need; `restart` restarts the daemon once no run is in
        progress; `announce` tells the apps the status changed."""
        self._root = root
        self._steps = steps
        self._restart = restart
        self._announce = announce
        self._checked: _Checked | None = None
        self._state, self._step, self._error = "idle", "", ""
        self._task: asyncio.Task | None = None
        # Held by a check and by starting an update, so two never fetch at once and a check never says "idle"
        # over an update that started while it fetched.
        self._lock = asyncio.Lock()
        # Set once the daemon is ending: no update starts any more.
        self._closed = False

    async def status(self) -> UpdateStatus:
        kind = installed_from(self._root)
        if kind != "git":
            return self._status(kind, _deployed(self._root), _Checked("", [], "", _NOT_A_CLONE[kind]))
        return self._status(kind, await self._current(), self._checked)

    async def check(self) -> UpdateStatus:
        """Fetches the upstream branch and says what's new on it."""
        async with self._lock:
            await self._check()
        return await self.status()

    async def start(self) -> UpdateStatus:
        """Starts installing what's new. Raises UpdateError when there's nothing to install or it can't be."""
        async with self._lock:
            if self._closed:
                raise UpdateError("lo9i is restarting or stopping. Update once it's back.")
            if self._state in ("updating", "restarting"):
                raise UpdateError("An update is already being installed.")
            status = await self._check()
            if not status.can_update:
                raise UpdateError(status.reason)
            if not status.behind:
                raise UpdateError("lo9i is up to date.")
            # Before the lock is let go, so the next start or check sees it.
            self._set("updating", _MERGE)
            self._task = asyncio.create_task(self._update(status.upstream))
        return await self.status()

    def installing(self) -> bool:
        """Whether an update is being installed or going back."""
        return self._task is not None and not self._task.done()

    async def until_installed(self) -> None:
        """Returns once no update is being installed: it finished, or failed and went back."""
        if self._task is not None:
            await asyncio.wait([self._task])

    def close(self) -> None:
        """The daemon is ending: no update starts any more. One in progress goes on (`until_installed`)."""
        self._closed = True

    async def _check(self) -> UpdateStatus:
        if installed_from(self._root) == "git" and self._state not in ("updating", "restarting"):
            self._set("checking")
            self._checked = await self._fetch()
            self._set("idle")
        return await self.status()

    async def recover(self) -> None:
        """At start: an update the daemon ended in the middle of goes back to the commit it came from, with what
        that one needs, and the daemon restarts on it; until then a restart or stop waits for it (`installing`)."""
        if installed_from(self._root) != "git" or not (before := await self._unfinished()):
            return
        async with self._lock:
            self._set("updating", f"{_UNFINISHED}: going back")
            self._task = asyncio.create_task(self._back_from(before))

    async def _update(self, upstream: str) -> None:
        merge = Step(_MERGE, ["git", "merge", "--ff-only", "--quiet", upstream])
        try:
            before = (await _git(self._root, "rev-parse", "HEAD")).strip()
            await self._mark(before)
            await self._run_step(merge)
        except _FailedError as e:
            await self._unmark()
            self._failed(f"{merge.label} failed: {e}")
            return
        for done, step in enumerate(self._steps):
            try:
                await self._run_step(step)
            except _FailedError as e:
                await self._failed_back(before, self._steps[: done + 1], f"{step.label} failed: {e}")
                return
        await self._unmark()
        logger.info("Updated to %s; restarting.", upstream)
        self._set("restarting")
        self._restart()

    async def _failed_back(self, before: str, ran: Sequence[Step], error: str) -> None:
        logger.warning("The update failed (%s); going back to %s.", error, before)
        if failed := await self._go_back(before, ran):
            label, why = failed
            self._failed(
                f"{error}. {label} failed too: {why}. A restart now would run a version that isn't fully installed."
            )
        else:
            self._failed(f"{error}. lo9i went back to the version it was on, which keeps running.")

    async def _back_from(self, before: str) -> None:
        """Every step runs again: which ones the unfinished update ran isn't known. The daemon restarts after, as
        it may have started on the code the update brought."""
        if (await _git(self._root, "rev-parse", "HEAD")).strip() == before:
            await self._unmark()  # It ended before the new commits came.
            self._set("idle")
            return
        logger.warning("%s; going back to %s.", _UNFINISHED, before)
        if failed := await self._go_back(before, self._steps):
            label, why = failed
            self._failed(f"{_UNFINISHED}, and {label} failed: {why}. It's tried again at the next start.")
            return
        self._set("restarting")
        self._restart()

    async def _go_back(self, before: str, ran: Sequence[Step]) -> tuple[str, str] | None:
        """Back to the commit the update came from, with what it needs: the steps that ran (the one that failed
        included) run again there; those after it never changed anything. Otherwise the next restart would run
        the new commits with what the old ones needed. The tree was clean before the update (`_blocker`), so
        whatever the steps changed in it is theirs. Returns the step that failed and why, or None once it's back
        and the mark is gone; a failure keeps the mark, so the next start tries again."""
        reset = Step("Going back to the version before", ["git", "reset", "--hard", "--quiet", before])
        for step in [reset, *(Step(f"Going back: {s.label}", s.command, s.timeout) for s in ran)]:
            try:
                await self._run_step(step)
            except _FailedError as e:
                return step.label, str(e)
        await self._unmark()
        return None

    async def _mark(self, before: str) -> None:
        mark = await self._mark_path()
        await asyncio.to_thread(mark.write_text, json.dumps({"before": before}) + "\n")

    async def _unmark(self) -> None:
        await asyncio.to_thread((await self._mark_path()).unlink, missing_ok=True)

    async def _unfinished(self) -> str:
        """The commit the update the daemon ended in the middle of came from, or "" when none did."""
        try:
            text = await asyncio.to_thread((await self._mark_path()).read_text)
            return str(json.loads(text)["before"])
        except (OSError, ValueError, KeyError, TypeError, _FailedError):
            return ""

    async def _mark_path(self) -> Path:
        """In the git folder, which a worktree has apart from its checkout. Raises _FailedError."""
        return self._root / (await _git(self._root, "rev-parse", "--git-path", _MARK)).strip()

    async def _run_step(self, step: Step) -> None:
        self._set("updating", step.label)
        await _run(self._root, step.command, step.timeout)

    def _failed(self, error: str) -> None:
        logger.warning("The update failed: %s", error)
        self._set("failed", error=error)

    async def _fetch(self) -> _Checked:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            upstream = (await _git(self._root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")).strip()
        except _FailedError:
            return _Checked(
                "", [], now, "This copy's branch follows no branch of the repository, so it has no updates."
            )
        try:
            await _git(self._root, "fetch", "--quiet")
        except _FailedError as e:
            return _Checked(upstream, [], now, f"Couldn't reach the repository: {e}")
        try:
            return await self._compared(upstream, now)
        except _FailedError as e:
            return _Checked(upstream, [], now, f"Couldn't compare this copy with {upstream}: {e}")

    async def _compared(self, upstream: str, now: str) -> _Checked:
        """What's new on the fetched upstream, and whether it can be installed. Raises _FailedError when git
        can't say."""
        new = _commits(await _git(self._root, "log", _FORMAT, f"-{_LISTED}", f"HEAD..{upstream}"))
        return _Checked(upstream, new, now, await self._blocker(upstream))

    async def _blocker(self, upstream: str) -> str:
        """Why the update can't be installed here, or "" when it can."""
        if (await _git(self._root, "status", "--porcelain", "--untracked-files=no")).strip():
            return "This copy has changes that aren't committed, which an update would overwrite. Commit or undo them."
        ahead = int((await _git(self._root, "rev-list", "--count", f"{upstream}..HEAD")).strip() or 0)
        if ahead:
            return f"This copy has {ahead} commit(s) {upstream} doesn't have. Push or drop them, then update."
        return ""

    async def _current(self) -> Commit | None:
        try:
            commits = _commits(await _git(self._root, "log", "-1", _FORMAT))
        except _FailedError:
            return None
        return commits[0] if commits else None

    def _status(self, kind: str, current: Commit | None, checked: _Checked | None) -> UpdateStatus:
        checked = checked or _Checked("", [], "", "")
        return UpdateStatus(
            installed_from=kind,
            current=current,
            upstream=checked.upstream,
            behind=len(checked.new),
            new=checked.new,
            checked_at=checked.checked_at,
            can_update=kind == "git" and bool(checked.checked_at) and not checked.reason,
            reason=checked.reason,
            state=self._state,
            step=self._step,
            error=self._error,
        )

    def _set(self, state: str, step: str = "", error: str = "") -> None:
        self._state, self._step, self._error = state, step, error
        self._announce()


_NOT_A_CLONE = {
    "deployed": "This copy was installed from another computer with scripts/deploy.sh. Deploy again from there.",
    "package": "This copy isn't a clone of lo9i's repository, so the app can't update it.",
}


def installed_from(root: Path) -> str:
    # In a git worktree .git is a file pointing at the main checkout.
    if (root / ".git").exists():
        return "git"
    return "deployed" if (root / VERSION_FILE).is_file() else "package"


def default_steps(root: Path) -> list[Step]:
    """Syncs the dependencies with uv, and builds the web app when npm is there (as install.sh does)."""
    found = uv.find()
    steps = [Step("Installing its dependencies", [found or "uv", "sync", "--frozen", "--inexact", "--quiet"])]
    npm = shutil.which("npm") or next((p for p in _NPM_PLACES if Path(p).is_file()), None)
    if npm is None:
        logger.info("npm isn't installed in %s; updates won't rebuild the web app.", root)
        return steps
    web = ["--prefix", "clients/web"]
    # `ci`, not `install`: install may rewrite the tracked package-lock.json, and a copy with changes not committed
    # takes no more updates (`_blocker`).
    return [
        *steps,
        Step("Installing the web app's packages", [npm, *web, "ci", "--no-audit", "--no-fund", "--silent"]),
        Step("Building the web app", [npm, *web, "run", "build", "--silent"]),
    ]


def repository_root() -> Path:
    """Where lo9i's files are: src/assistant/daemon/updates.py is three folders down."""
    return Path(__file__).resolve().parents[3]


def write_version(root: Path, commit: Commit) -> None:
    """For scripts/deploy.sh: the commit the copy it makes comes from."""
    (root / VERSION_FILE).write_text(json.dumps(asdict(commit)) + "\n")


def _deployed(root: Path) -> Commit | None:
    try:
        return Commit(**json.loads((root / VERSION_FILE).read_text()))
    except (OSError, ValueError, TypeError):
        return None


def _commits(log: str) -> list[Commit]:
    return [Commit(*line.split("\x1f", 2)) for line in log.splitlines() if line.count("\x1f") == 2]


async def _git(root: Path, *args: str) -> str:
    return await _run(root, ["git", *args], _GIT_SECONDS)


async def _run(root: Path, command: list[str], timeout: float) -> str:
    """The command's output; raises _FailedError with the last line it wrote when it fails."""
    # Never wait on a prompt for a password: there's no one at a terminal to answer it.
    env = os.environ | {"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    try:
        process = await asyncio.create_subprocess_exec(
            *command, cwd=root, env=env, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )  # fmt: skip
    except OSError as e:
        raise _FailedError(f"{command[0]} couldn't run ({e.strerror or e})") from e
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        raise _FailedError(f"it took longer than {int(timeout)} seconds") from None
    finally:
        await _ended(process)
    if process.returncode:
        raise _FailedError(_last_line(err.decode(errors="replace") or out.decode(errors="replace")))
    return out.decode(errors="replace")


async def _ended(process: asyncio.subprocess.Process) -> None:
    """Kills the command if it still runs: it took too long, or its task was cancelled, and left running it would
    go on changing the tree after the update stopped following it."""
    if process.returncode is None:
        process.kill()
        await process.wait()


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "it stopped with an error"


async def _this_version(root: Path) -> Commit:
    commit = _commits(await _git(root, "log", "-1", _FORMAT))[0]
    if (await _git(root, "status", "--porcelain", "--untracked-files=no")).strip():
        return Commit(commit.sha, f"{commit.subject} (with changes not committed)", commit.date)
    return commit


def main() -> None:
    """`python -m assistant.daemon.updates`, from scripts/deploy.sh: writes the commit this checkout is at into
    it, for the copy deploy.sh makes."""
    root = repository_root()
    write_version(root, asyncio.run(_this_version(root)))


if __name__ == "__main__":
    main()
