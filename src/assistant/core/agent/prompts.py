"""The system prompt texts the user edits, from any client (Settings → System prompt)."""

from assistant.core.agent.base import ServiceBase
from assistant.core.conversation import prompt_edits
from assistant.core.conversation.prompt_edits import PromptEditError, PromptSection, UnknownPromptError

__all__ = ["PromptEditError", "PromptSection", "PromptsMixin", "UnknownPromptError"]


class PromptsMixin(ServiceBase):
    async def prompt_sections(self) -> list[PromptSection]:
        return await prompt_edits.sections()

    async def save_prompt(self, name: str, text: str) -> PromptSection:
        """Used from the next user message in each conversation. Raises UnknownPromptError, PromptEditError."""
        saved = await prompt_edits.save(name, text)
        self.bus.publish("prompts")
        return saved

    async def reset_prompt(self, name: str) -> PromptSection:
        """Back to the built-in text. Raises UnknownPromptError, PromptEditError."""
        reset = await prompt_edits.reset(name)
        self.bus.publish("prompts")
        return reset
