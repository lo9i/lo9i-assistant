import asyncio
import contextlib
import os
import pwd
import shlex
import shutil
import signal
from pathlib import Path

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.config import settings
from assistant.core.context import Context
from assistant.core.tools.approval import ask
from assistant.core.tools.bash_guard import find_danger
from assistant.core.tools.registry import register

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
    workspace = Path(settings.workspace_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        command,
        cwd=workspace,
        env=_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        # Its own process group, so stopping it also stops the commands it started.
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=settings.bash_timeout)
    except TimeoutError:
        await _kill(proc)
        return f"Timed out after {settings.bash_timeout}s.", {"exit_code": None}
    except asyncio.CancelledError:
        await _kill(proc)
        raise
    output = f"exit code: {proc.returncode}\n{_truncate(stdout.decode(errors='replace'))}"
    return output, {"exit_code": proc.returncode}


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


async def _kill(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    await proc.wait()


def _truncate(output: str) -> str:
    if len(output) <= settings.bash_max_output:
        return output
    return output[: settings.bash_max_output] + "\n[output truncated]"
