"""The bash sandbox's text (Markdown), shared by its settings section and the plain REPL."""

from lo9i.core.agent import SandboxStatus
from lo9i_terminal.i18n import t


def describe(status: SandboxStatus, error: str) -> str:
    parts = [
        "## " + t("Command sandbox"),
        t(
            "Runs the assistant's shell commands in a container that sees only its workspace, never lo9i's data or "
            "your other files. For every device."
        ),
        _state(status),
    ]
    if error:
        parts.append(f"**{error}**")
    return "\n\n".join(parts)


def _state(status: SandboxStatus) -> str:
    runtime = "Podman" if status.runtime == "podman" else "Docker"
    if status.problem:
        state = t("On") if status.enabled else t("Off, and it can't be turned on")
        return f"{state}: {status.problem} {status.fix}"
    if status.enabled:
        return t(
            "On: commands run in {runtime}, image {image}, with only the workspace.",
            runtime=runtime,
            image=status.image,
        )
    return t("Off: commands run on this computer. {runtime} is available to run them in a sandbox.", runtime=runtime)
