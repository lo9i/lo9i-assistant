import asyncio
import contextlib
import os
import pwd
import shlex
import shutil
import signal
from collections.abc import Awaitable, Callable
from pathlib import Path

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from lo9i.core.config import settings
from lo9i.core.context import Context, require_store
from lo9i.core.sandbox import container
from lo9i.core.sandbox import runtime as runtimes
from lo9i.core.sandbox import setting as sandbox_setting
from lo9i.core.tools.approval import ask
from lo9i.core.tools.bash_guard import find_danger
from lo9i.core.tools.registry import register

# Commands run with a minimal environment so they can't read the app's secrets
# (Anthropic key, database URL, Langfuse keys) from env vars.
_SAFE_PATH = "/opt/homebrew/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_GITHUB_HELPER = "credential.https://github.com.helper"


# The artifact of a call that ran: {"exit_code": n}, with None when it timed out. Callbacks read it
# (core/skills/tracker.py); the model sees only the text.
Artifact = dict[str, int | None] | None


@register("terminal", subagents=True)
@tool(response_format="content_and_artifact")
async def bash(command: str, runtime: ToolRuntime[Context]) -> tuple[str, Artifact]:
    """Run a bash command in the workspace directory and return exit code and output.

    Use it for file operations, scripts, and inspecting the environment. Each call
    is a fresh shell: `cd` and exported variables don't persist between calls.
    """
    rejection = _request_approval(command, runtime.context)
    if rejection:
        return rejection, None
    if await sandbox_setting.enabled(require_store(runtime.store)):
        return await _in_sandbox(command)
    return await _run(command)


def _approval_reason(command: str) -> str | None:
    if settings.bash_approval == "always":
        return "all commands require approval"
    if settings.bash_approval == "dangerous":
        return find_danger(command)
    return None


def _request_approval(command: str, context: Context) -> str | None:
    """Pause for approval when needed. Returns a message for the model if rejected."""
    reason = _approval_reason(command)
    return None if reason is None else ask({"tool": "bash", "command": command, "reason": reason}, context)


async def _run(command: str) -> tuple[str, Artifact]:
    workspace = _workspace()
    output, exit_code = await _execute(["bash", "-c", command], workspace, _environment())
    return _shown(output, exit_code), {"exit_code": exit_code}


async def _in_sandbox(command: str) -> tuple[str, Artifact]:
    """In a container with only the workspace (core/sandbox/); never on this computer when it can't."""
    workspace, found = _workspace(), runtimes.find()
    if found is None:
        return container.no_runtime(), None
    if refused := container.refusal(workspace):
        return refused, None
    name = container.name()
    argv = container.argv(found, workspace, name, command)
    output, exit_code = await _execute(argv, workspace, runtimes.environment(), lambda: container.remove(found, name))
    if exit_code is None:
        return _shown(output, exit_code), {"exit_code": None}
    if container.not_started(exit_code):
        return await container.why_not_started(found, output), None
    return _shown(container.explained(found, exit_code, output), exit_code), {"exit_code": exit_code}


def _workspace() -> Path:
    workspace = Path(settings.workspace_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


async def _execute(
    argv: list[str], cwd: Path, env: dict[str, str], stopped: Callable[[], Awaitable[None]] | None = None
) -> tuple[str, int | None]:
    """Its output and exit code; None for the code when it timed out. `stopped` cleans up after it's killed."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        # Its own process group, so stopping it also stops the commands it started.
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=settings.bash_timeout)
    except (TimeoutError, asyncio.CancelledError) as e:
        await _kill(proc, stopped)
        if isinstance(e, asyncio.CancelledError):
            raise
        return "", None
    return stdout.decode(errors="replace"), proc.returncode


def _shown(output: str, exit_code: int | None) -> str:
    if exit_code is None:
        return f"Timed out after {settings.bash_timeout}s."
    return f"exit code: {exit_code}\n{_truncate(output)}"


def _environment() -> dict[str, str]:
    return {"PATH": _SAFE_PATH, "HOME": _home(), "LANG": "C.UTF-8", **_github_credentials()}


def _home() -> str:
    """The user's home from the password database, not the daemon's HOME, which a service manager
    may set or leave out: git, gh and ssh find the user's config and logins there."""
    return pwd.getpwuid(os.getuid()).pw_dir


def _github_credentials() -> dict[str, str]:
    """git over HTTPS to GitHub signs in through gh when it's installed, even without
    `gh auth setup-git`. Added after the user's own helpers, so one they set is asked first."""
    gh = shutil.which("gh", path=_SAFE_PATH)
    if gh is None:
        return {}
    helper = f"!{shlex.quote(gh)} auth git-credential"
    return {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": _GITHUB_HELPER, "GIT_CONFIG_VALUE_0": helper}


async def _kill(proc: asyncio.subprocess.Process, stopped: Callable[[], Awaitable[None]] | None) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    await proc.wait()
    if stopped is not None:
        await asyncio.shield(stopped())


def _truncate(output: str) -> str:
    if len(output) <= settings.bash_max_output:
        return output
    return output[: settings.bash_max_output] + "\n[output truncated]"
