"""What the apps and the setup check show of the sandbox, and getting it ready to turn on: it can't be without a
container runtime that answers, and turning it on downloads its image first, so the first command doesn't spend its
time limit on that."""

from dataclasses import dataclass

from langgraph.store.base import BaseStore

from lo9i.core.config import settings
from lo9i.core.i18n import said
from lo9i.core.sandbox import runtime as runtimes
from lo9i.core.sandbox import setting
from lo9i.core.sandbox.runtime import Runtime

_PULL_SECONDS = 600


class SandboxUnavailableError(Exception):
    """It can't be turned on now; the message says why and what to do, in plain words."""


@dataclass
class SandboxStatus:
    enabled: bool
    # docker or podman, "" when neither is installed.
    runtime: str
    # Whether it can run containers now.
    available: bool
    # Why it isn't available and what to do, "" when it is.
    problem: str
    fix: str
    image: str


async def status(store: BaseStore) -> SandboxStatus:
    found = runtimes.find()
    answering = found is not None and await runtimes.answering(found)
    problem, fix = _problem(found, answering)
    name = found.name if found else ""
    return SandboxStatus(await setting.enabled(store), name, answering, problem, fix, settings.bash_sandbox_image)


async def ready() -> None:
    """Raises SandboxUnavailableError when there's no runtime that answers or it can't download the image."""
    found = runtimes.find()
    if found is None or not await runtimes.answering(found):
        problem, fix = _problem(found, False)
        raise SandboxUnavailableError(said("{problem} {fix}", problem=problem, fix=fix))
    if await runtimes.ask(found, "pull", settings.bash_sandbox_image, seconds=_PULL_SECONDS) is None:
        raise SandboxUnavailableError(
            said(
                "{runtime} couldn't download the sandbox's image ({image}). Check the internet connection, then try "
                "again.",
                runtime=found.title,
                image=settings.bash_sandbox_image,
            )
        )


def _problem(found: Runtime | None, answering: bool) -> tuple[str, str]:
    if found is None:
        return runtimes.missing(), runtimes.install_fix()
    if not answering:
        return runtimes.not_running(found), runtimes.start_fix(found)
    return "", ""
