"""A paired device installing from a repository: the owner approves what runs code on this computer (a local server, a
skill with scripts) before anything is copied in; what runs nothing installs as before."""

from pathlib import Path
from typing import Any

import pytest

from lo9i.core.mcp import servers
from lo9i.core.mcp.owner_approval import NotApprovedError
from tests.core.test_repositories import HELLO, URL, repo  # noqa: F401 (a fixture, used by `remote`)


@pytest.fixture
def remote(repo: Path) -> Path:  # noqa: F811
    return repo


class _Owner:
    def __init__(self, service, approved: bool) -> None:
        self._service, self._approved = service, approved
        self.asked: list[dict[str, Any]] = []

    async def forward(self, interrupt_id: str, title: str, request: dict[str, Any]) -> None:
        self.asked.append(request)
        self._service.approvals.answer(interrupt_id, {"approved": self._approved})


async def _installed(service) -> list[str]:
    return [s.name for s in await servers.load_all(service._storage.store)]


async def test_a_local_server_a_device_installs_waits_for_the_owner(service, remote):
    owner = _Owner(service, approved=False)
    service.approvals.register("telegram", owner)
    with pytest.raises(NotApprovedError):
        await service.install_from_repository(URL, ["expenses"], [HELLO], asked_by="Laptop")
    assert await _installed(service) == []
    assert (
        "hello:" in owner.asked[0]["command"] and "expenses: a skill with scripts/add.py" in owner.asked[0]["command"]
    )


async def test_what_the_owner_approves_installs(service, remote):
    service.approvals.register("telegram", _Owner(service, approved=True))
    await service.install_from_repository(URL, [], [HELLO], asked_by="Laptop")
    assert await _installed(service) == ["hello"]


async def test_what_runs_nothing_installs_without_asking(service, remote):
    installed = await service.install_from_repository(URL, ["news-digest"], [], asked_by="Laptop")
    assert [s.name for s in installed.skills] == ["news-digest"]


async def test_the_owner_on_this_computer_isnt_asked(service, remote):
    await service.install_from_repository(URL, [], [HELLO])
    assert await _installed(service) == ["hello"]
