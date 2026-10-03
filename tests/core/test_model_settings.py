"""The model set from the app: its provider's package installed if needed, checked before it's
saved, used at once, kept across restarts, overriding .env until it's reset. Secrets are never
shown."""

import pytest
from langchain_core.messages import AIMessage

import assistant.core.agent.model as model_module
import assistant.core.graph as graph_module
from assistant.core.agent import AssistantService, ModelSettingsError
from assistant.core.config import settings
from assistant.core.llm import packages
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.packages import PackageError
from tests.conftest import collect


class _Checked:
    """Stands in for build_llm in the check: answers OK, or fails for models in `failing`."""

    def __init__(self) -> None:
        self.failing: set[str] = set()
        self.checked: list[tuple[str, str, str]] = []

    def __call__(self, choice: ModelChoice, model: str):
        outer = self

        class _Model:
            async def ainvoke(self, messages, config=None):
                outer.checked.append((choice.provider, choice.values.get("api_key", ""), model))
                if model in outer.failing:
                    raise RuntimeError("401 invalid x-api-key")
                return AIMessage("OK")

        return _Model()


@pytest.fixture
def checked(monkeypatch) -> _Checked:
    fake = _Checked()
    monkeypatch.setattr(model_module, "build_llm", fake)
    return fake


@pytest.fixture
def used(monkeypatch, script) -> list[ModelChoice]:
    """The choices the graph was built with."""
    choices: list[ModelChoice] = []

    def build(choice, model):
        choices.append(choice)
        return script.model()

    monkeypatch.setattr(graph_module, "build_llm", build)
    return choices


async def test_env_settings_apply_until_the_app_sets_a_model(service, monkeypatch):
    status = await service.model_status()
    assert (status.source, status.provider, status.model) == ("env", settings.provider, settings.model)


def _key(key: str) -> dict[str, str]:
    return {"api_key": key}


async def test_a_checked_model_is_saved_and_used_at_once(service, script, checked, used):
    status = await service.set_model("copilot", _key("gh-token"), "claude-opus-5.5", "claude-sonnet-5.5")
    assert (status.source, status.provider, status.secrets_set, status.values) == ("app", "copilot", ["api_key"], {})
    assert "gh-token" not in repr(status)
    assert checked.checked == [("copilot", "gh-token", "claude-opus-5.5"), ("copilot", "gh-token", "claude-sonnet-5.5")]
    script.reply("hi")
    await collect(service.send(await service.session("owner", "cli"), "hello"))
    assert used[-1] == ModelChoice("copilot", "claude-opus-5.5", "claude-sonnet-5.5", _key("gh-token"))


async def test_a_model_that_doesnt_answer_isnt_saved(service, checked):
    checked.failing = {"claude-sonnet-5.5"}
    with pytest.raises(ModelSettingsError, match=r"claude-sonnet-5\.5 didn.t answer: 401 invalid x-api-key"):
        await service.set_model("copilot", _key("bad"), "claude-opus-5.5", "claude-sonnet-5.5")
    assert (await service.model_status()).source == "env"


async def test_changing_models_keeps_the_secrets_of_the_same_provider(service, checked):
    await service.set_model("anthropic", _key("sk-1"), "claude-opus-5-5", "claude-sonnet-5-5")
    await service.set_model("anthropic", {}, "claude-sonnet-5-5", "claude-sonnet-5-5")
    assert checked.checked[-1] == ("anthropic", "sk-1", "claude-sonnet-5-5")
    with pytest.raises(ModelSettingsError, match="Enter the GitHub token"):
        await service.set_model("copilot", {}, "claude-opus-5.5", "claude-sonnet-5.5")


async def test_incomplete_settings_are_refused(service, checked):
    with pytest.raises(ModelSettingsError, match="Unknown provider"):
        await service.set_model("gemini", _key("k"), "m", "m")
    with pytest.raises(ModelSettingsError, match="both models"):
        await service.set_model("openai", {"api_key": "k", "base_url": "http://localhost:11434/v1"}, "qwen3", "")
    with pytest.raises(ModelSettingsError, match="Enter the Secret access key"):
        await service.set_model("bedrock_converse", {"region_name": "us-east-1", "aws_access_key_id": "a"}, "m", "m")
    assert checked.checked == []


async def test_the_choice_survives_a_restart_and_reset_goes_back_to_env(service, checked, script, digests, titles):
    await service.set_model("openai", {"api_key": "k", "base_url": "http://localhost:11434/v1"}, "qwen3", "qwen3")
    async with AssistantService.open() as restarted:
        status = await restarted.model_status()
        assert (status.source, status.provider, status.values) == (
            "app",
            "openai",
            {"base_url": "http://localhost:11434/v1"},
        )
        status = await restarted.reset_model()
        assert (status.source, status.provider) == ("env", settings.provider)


async def test_secrets_are_kept_encrypted_apart_from_the_settings(service, checked):
    await service.set_model("anthropic", _key("sk-secret"), "claude-opus-5-5", "claude-sonnet-5-5")
    record = await service.store.aget(("settings",), "model")
    secret = await service.store.aget(("secrets",), "model:secrets")
    assert record is not None and "sk-secret" not in str(record.value)
    assert secret is not None and "sk-secret" not in str(secret.value)
    await service.reset_model()
    assert await service.store.aget(("secrets",), "model:secrets") is None


async def test_a_choice_saved_before_providers_had_fields_is_moved_over(service):
    from assistant.core import secret_store
    from assistant.core.llm import choice

    old = {"provider": "openai", "api_key": "", "base_url": "http://x/v1", "model": "m", "worker_model": "w"}
    await service.store.aput(("settings",), "model", old)
    await secret_store.put(service.store, service.secrets, "model:api_key", "sk-old")
    await choice.migrate(service.store, service.secrets)
    assert await service.store.aget(("secrets",), "model:api_key") is None
    current = await choice.current(service.store, service.secrets)
    assert current == ModelChoice("openai", "m", "w", {"api_key": "sk-old", "base_url": "http://x/v1"})


@pytest.fixture
def installs(monkeypatch) -> list[str]:
    """Stands in for installing packages: records them, and they're installed from then on."""
    done: list[str] = []

    async def ensure(provider):
        if provider.package and provider.package not in done:
            done.append(provider.package)

    monkeypatch.setattr(packages, "ensure", ensure)
    monkeypatch.setattr(packages, "installed", lambda provider: not provider.package or provider.package in done)
    return done


async def test_any_langchain_provider_is_installed_then_checked_and_saved(service, checked, installs):
    providers = {p.id: p for p in service.model_providers()}
    assert not providers["groq"].installed and providers["azure_openai"].installed
    values = {"region_name": "us-east-1", "aws_access_key_id": "AKIA", "aws_secret_access_key": "s3"}
    status = await service.set_model("bedrock_converse", values, "anthropic.claude", "anthropic.claude")
    assert installs == ["langchain-aws>=1.8,<2"] and checked.checked[0][0] == "bedrock_converse"
    assert (status.values, status.secrets_set) == (
        {"region_name": "us-east-1"},
        ["aws_access_key_id", "aws_secret_access_key"],
    )
    assert {p.id: p for p in service.model_providers()}["bedrock_converse"].installed


async def test_a_package_that_wont_install_leaves_the_model_as_it_was(service, checked, monkeypatch):
    async def fail(provider):
        raise PackageError("Couldn't install it: no network")

    monkeypatch.setattr(packages, "ensure", fail)
    with pytest.raises(ModelSettingsError, match="no network"):
        await service.set_model("groq", _key("k"), "llama", "llama")
    assert (await service.model_status()).source == "env" and checked.checked == []


async def test_a_saved_provider_whose_package_is_gone_falls_back_to_env_at_start(
    service, checked, installs, monkeypatch, script, digests, titles
):
    await service.set_model("groq", _key("k"), "llama", "llama")

    async def gone(provider):
        raise PackageError("Couldn't install it: no network")

    monkeypatch.setattr(packages, "ensure", gone)
    async with AssistantService.open() as restarted:
        assert (await restarted.model_status()).provider == settings.provider
