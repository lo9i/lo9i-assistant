"""The model set from the app: checked before it's saved, used at once, kept across restarts,
overriding .env until it's reset. The key is never shown."""

import pytest
from langchain_core.messages import AIMessage

import assistant.core.agent.model as model_module
import assistant.core.graph as graph_module
from assistant.core.agent import AssistantService, ModelSettingsError
from assistant.core.config import settings
from assistant.core.llm.choice import ModelChoice
from tests.conftest import collect


class _Checked:
    """Stands in for build_llm in the check: answers OK, or fails for models in `failing`."""

    def __init__(self) -> None:
        self.failing: set[str] = set()
        self.checked: list[tuple[str, str, str]] = []

    def __call__(self, choice: ModelChoice, model: str):
        outer = self

        class _Model:
            async def ainvoke(self, messages):
                outer.checked.append((choice.provider, choice.api_key, model))
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


async def test_a_checked_model_is_saved_and_used_at_once(service, script, checked, used):
    status = await service.set_model("copilot", "gh-token", "", "claude-opus-5.5", "claude-sonnet-5.5")
    assert (status.source, status.provider, status.key_set) == ("app", "copilot", True)
    assert "gh-token" not in repr(status)
    assert checked.checked == [("copilot", "gh-token", "claude-opus-5.5"), ("copilot", "gh-token", "claude-sonnet-5.5")]
    script.reply("hi")
    await collect(service.send(await service.session("owner", "cli"), "hello"))
    assert used[-1] == ModelChoice("copilot", "gh-token", "", "claude-opus-5.5", "claude-sonnet-5.5")


async def test_a_model_that_doesnt_answer_isnt_saved(service, checked):
    checked.failing = {"claude-sonnet-5.5"}
    with pytest.raises(ModelSettingsError, match=r"claude-sonnet-5\.5 didn.t answer: 401 invalid x-api-key"):
        await service.set_model("copilot", "bad", "", "claude-opus-5.5", "claude-sonnet-5.5")
    assert (await service.model_status()).source == "env"


async def test_changing_models_keeps_the_key_of_the_same_provider(service, checked):
    await service.set_model("anthropic", "sk-1", "", "claude-opus-5-5", "claude-sonnet-5-5")
    await service.set_model("anthropic", "", "", "claude-sonnet-5-5", "claude-sonnet-5-5")
    assert checked.checked[-1] == ("anthropic", "sk-1", "claude-sonnet-5-5")
    with pytest.raises(ModelSettingsError, match="Enter the GitHub token"):
        await service.set_model("copilot", "", "", "claude-opus-5.5", "claude-sonnet-5.5")


async def test_incomplete_settings_are_refused(service, checked):
    with pytest.raises(ModelSettingsError, match="Unknown provider"):
        await service.set_model("gemini", "k", "", "m", "m")
    with pytest.raises(ModelSettingsError, match="both models"):
        await service.set_model("openai", "k", "http://localhost:11434/v1", "qwen3", "")
    assert checked.checked == []


async def test_the_choice_survives_a_restart_and_reset_goes_back_to_env(service, checked, script, digests, titles):
    await service.set_model("openai", "k", "http://localhost:11434/v1", "qwen3", "qwen3")
    async with AssistantService.open() as restarted:
        status = await restarted.model_status()
        assert (status.source, status.provider, status.base_url) == ("app", "openai", "http://localhost:11434/v1")
        status = await restarted.reset_model()
        assert (status.source, status.provider) == ("env", settings.provider)
