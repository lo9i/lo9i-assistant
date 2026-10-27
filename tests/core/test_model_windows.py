"""A conversation's context is measured against its model's context window where the provider says it: learned
once and kept; EPOCH_MAX_TOKENS where it isn't known. Compaction doesn't follow it."""

from datetime import date
from typing import Any

from assistant.core.config import settings
from assistant.core.llm import copilot
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.windows import ContextWindows
from tests.conftest import collect

OPUS = ModelChoice("anthropic", "claude-opus-5-5", "claude-sonnet-5-5")


def _counting(answers: list[Any]) -> tuple[Any, list[str]]:
    asked: list[str] = []

    async def lookup(choice: ModelChoice, model: str) -> int | None:
        asked.append(model)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return lookup, asked


async def test_a_window_is_learned_once_and_kept(service, model_windows):
    model_windows["anthropic"], asked = _counting([1_000_000])
    assert await ContextWindows(service.store).of(OPUS) == 1_000_000
    assert await ContextWindows(service.store).of(OPUS) == 1_000_000  # kept: another instance doesn't ask
    assert asked == ["claude-opus-5-5"]


async def test_an_unknown_window_is_the_epochs_limit_and_isnt_asked_again(service, model_windows):
    model_windows["copilot"], asked = _counting([copilot.CopilotAuthError("rejected"), 200_000])
    windows = ContextWindows(service.store)
    choice = ModelChoice("copilot", "claude-opus-5.5", "claude-sonnet-5.5")
    assert await windows.of(choice) == await windows.of(choice) == settings.epoch_max_tokens
    assert asked == ["claude-opus-5.5"]
    assert await windows.of(ModelChoice("openai", "llama", "llama")) == settings.epoch_max_tokens


async def test_the_context_bar_and_the_health_check_measure_against_the_models_window(service, script, model_windows):
    model_windows["anthropic"], _ = _counting([1_000_000])
    script.reply("hi")
    session = await service.session("owner", "cli")
    await collect(service.send(session, "hello"))
    assert (await service.conversation_stats("owner", session.thread_id)).context_limit == 1_000_000
    report = await service.doctor.check("owner", date.today(), whole_day=False)
    assert report.context.window == 1_000_000
