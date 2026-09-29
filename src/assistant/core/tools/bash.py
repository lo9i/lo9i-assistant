import asyncio
from pathlib import Path

from langchain_core.tools import tool
from langgraph.types import interrupt

from assistant.core.config import settings
from assistant.core.tools.bash_guard import find_danger
from assistant.core.tools.registry import register

# Commands run with a minimal environment so they can't read the app's secrets
# (Anthropic key, database URL, Langfuse keys) from env vars.
_SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


@register("terminal")
@tool
async def bash(command: str) -> str:
    """Run a bash command in the workspace directory and return exit code and output.

    Use it for file operations, scripts, and inspecting the environment. Each call
    is a fresh shell: `cd` and exported variables don't persist between calls.
    """
    rejection = _request_approval(command)
    if rejection:
        return rejection
    return await _run(command)


def _approval_reason(command: str) -> str | None:
    if settings.bash_approval == "always":
        return "all commands require approval"
    if settings.bash_approval == "dangerous":
        return find_danger(command)
    return None


def _request_approval(command: str) -> str | None:
    """Pause for approval when needed. Returns a message for the model if rejected."""
    reason = _approval_reason(command)
    if reason is None:
        return None
    decision = interrupt({"tool": "bash", "command": command, "reason": reason})
    if decision.get("approved"):
        return None
    return f"The user rejected this command ({decision.get('reason') or 'no reason given'})."


async def _run(command: str) -> str:
    workspace = Path(settings.workspace_dir).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        command,
        cwd=workspace,
        env={"PATH": _SAFE_PATH, "HOME": str(workspace), "LANG": "C.UTF-8"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=settings.bash_timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return f"Timed out after {settings.bash_timeout}s."
    return f"exit code: {proc.returncode}\n{_truncate(stdout.decode(errors='replace'))}"


def _truncate(output: str) -> str:
    if len(output) <= settings.bash_max_output:
        return output
    return output[: settings.bash_max_output] + "\n[output truncated]"
