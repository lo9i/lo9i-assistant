"""Installing a model provider's package when it's first chosen. uv itself is replaced."""

import sys

import pytest

from assistant.core.llm import packages
from assistant.core.llm.packages import PackageError
from assistant.core.llm.providers import provider


@pytest.fixture
def uv(monkeypatch) -> list[tuple[str, ...]]:
    commands: list[tuple[str, ...]] = []

    async def run(*command: str) -> None:
        commands.append(command)

    monkeypatch.setattr(packages, "find_uv", lambda: "/opt/uv")
    monkeypatch.setattr(packages, "_run", run)
    return commands


async def test_a_missing_package_is_installed_into_the_daemons_python_keeping_langchain_core(uv, monkeypatch):
    found = iter([False, True])
    monkeypatch.setattr(packages, "installed", lambda p: next(found))
    groq = provider("groq")
    assert groq is not None
    await packages.ensure(groq)
    [command] = uv
    assert command[:5] == ("/opt/uv", "pip", "install", "--python", sys.executable)
    assert command[5] == "langchain-groq>=1.1,<2" and command[6].startswith("langchain-core==")


async def test_providers_that_ship_with_the_assistant_install_nothing(uv):
    for provider_id in ("anthropic", "copilot", "openai", "azure_openai"):
        known = provider(provider_id)
        assert known is not None and packages.installed(known)
        await packages.ensure(known)
    assert uv == []


async def test_without_uv_or_a_working_package_it_says_why(uv, monkeypatch):
    groq = provider("groq")
    assert groq is not None
    monkeypatch.setattr(packages, "installed", lambda p: False)
    with pytest.raises(PackageError, match="still can't be imported"):
        await packages.ensure(groq)
    monkeypatch.setattr(packages, "find_uv", lambda: None)
    with pytest.raises(PackageError, match="needs uv"):
        await packages.ensure(groq)


def test_every_provider_names_a_package_for_its_module():
    from assistant.core.llm.providers import LANGCHAIN_PROVIDERS

    for p in LANGCHAIN_PROVIDERS:
        if p.package:
            assert p.package.split(">=")[0] == p.module.replace("_", "-"), p.id
