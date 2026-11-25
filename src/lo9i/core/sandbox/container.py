"""Running one bash command in a container: the workspace mounted at /workspace and nothing else of this computer,
the user's own uid so what it writes there is theirs, no added privileges. Each command a container of its own, named
so it can be removed when the command is stopped (stopping the runtime's command leaves the container running).
When a command didn't run there, or failed in a way the sandbox explains, the text says so in plain words, for the
model to tell the user."""

import os
import uuid
from pathlib import Path

from lo9i.core.config import settings
from lo9i.core.sandbox import runtime as runtimes
from lo9i.core.sandbox.runtime import Runtime

MOUNTED = "/workspace"
# `docker run` and `podman run` exit with it when the container couldn't be started (the runtime's own error).
_NOT_STARTED = 125
_REMOVE_SECONDS = 30


def data_folder() -> Path:
    return Path(settings.database_path).expanduser().resolve().parent


def no_runtime() -> str:
    return (
        "The sandbox is on in Settings → General, but neither Docker nor Podman is installed on this computer, so the "
        f"command didn't run. {runtimes.install_fix()} Or turn the sandbox off there."
    )


def refusal(workspace: Path) -> str | None:
    """Why a command can't run in the sandbox with this workspace, or None when it can."""
    if data_folder().is_relative_to(workspace):
        return (
            f"The workspace folder ({workspace}) holds lo9i's data folder, so the sandbox won't mount it and the "
            "command didn't run. Set the workspace to a folder of its own, or turn the sandbox off in Settings → "
            "General."
        )
    return None


def name() -> str:
    return f"lo9i-bash-{uuid.uuid4().hex[:12]}"


def argv(found: Runtime, workspace: Path, container: str, command: str) -> list[str]:
    return [
        found.path,
        "run",
        "--rm",
        "--name",
        container,
        *_user(found),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--volume",
        f"{workspace}:{MOUNTED}",
        "--workdir",
        MOUNTED,
        "--env",
        "HOME=/tmp",
        "--env",
        "LANG=C.UTF-8",
        settings.bash_sandbox_image,
        "bash",
        "-c",
        command,
    ]


def _user(found: Runtime) -> list[str]:
    """Podman without root maps the user to root in the container, and keep-id to themself; Docker takes the uid."""
    if found.name == "podman":
        return ["--userns", "keep-id"]
    return ["--user", f"{os.getuid()}:{os.getgid()}"]


async def remove(found: Runtime, container: str) -> None:
    await runtimes.ask(found, "rm", "--force", container, seconds=_REMOVE_SECONDS)


def not_started(exit_code: int) -> bool:
    return exit_code == _NOT_STARTED


async def why_not_started(found: Runtime, output: str) -> str:
    """Why the container didn't start, `output` being the runtime's error."""
    if not await runtimes.answering(found):
        return (
            f"The sandbox is on, but {found.title} isn't running, so the command didn't run. "
            f"{runtimes.start_fix(found)} Or turn the sandbox off in Settings → General."
        )
    return f"The sandbox couldn't start a container ({found.title}), so the command didn't run. It said:\n{output}"


def explained(found: Runtime, exit_code: int, output: str) -> str:
    """`output` with what the sandbox may have had to do with a failure."""
    if exit_code == 0:
        return output
    return (
        f"{output}\n[This ran in the sandbox ({found.title}, image {settings.bash_sandbox_image}): only the workspace "
        f"is there, at {MOUNTED}. This computer's other files, lo9i's data among them, and the programs installed on "
        "it aren't, so a command that needs them fails here.]"
    )
