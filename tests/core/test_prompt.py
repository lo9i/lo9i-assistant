"""System prompt contents: persona file, channel hints, prompt files."""

from assistant.core.conversation import prompts
from assistant.core.conversation.prompt import build_system_prompt


async def test_persona_file_replaces_the_default(service, isolated_settings):
    (isolated_settings / "SOUL.md").write_text("You are Lo9i. Be terse.\n")
    prompt = await build_system_prompt(service._storage.store, "u", "", "")
    assert prompt.startswith("You are Lo9i. Be terse.")


async def test_default_persona_and_channel_hints(service):
    prompt = await build_system_prompt(service._storage.store, "u", "", "")
    assert prompt.startswith(prompts.load("persona"))
    assert "- telegram:" in prompt and "- cli:" in prompt


def test_digest_prompt_has_its_placeholders():
    assert all(
        f"{{{name}}}" in prompts.load("digest") for name in ["previous_summary", "profile", "facts", "transcript"]
    )
