"""Named subagents plugins bring (`subagent:` in server.yaml, core/mcp/subagents.py): listed in the system prompt,
handed tasks with delegate's `agent`, each working with its own instructions, model and tools."""

from langchain_core.messages import SystemMessage

from assistant.core import subagent as subagent_module
from assistant.core.agent import McpServerChanges, ServerValues
from assistant.core.conversation.prompt import build_system_prompt
from assistant.core.events import ToolFinished
from assistant.core.mcp import subagents
from tests.conftest import collect
from tests.core.test_repositories import URL, _problems, _write, repo  # noqa: F401 (a fixture, used by `researcher`)

_RESEARCHER = """
description: A researcher
format: 6
subagent:
  name: researcher
  description: Researches a question across many web pages and answers with its sources.
  prompt: prompt.md
  model: main
  tools: [web_search, web_extract]
"""
_PROMPT = "You research. Cite every source as a link."


async def _install(service, repo, yaml: str = _RESEARCHER) -> None:  # noqa: F811
    _write(repo / "assistant" / "agents" / "researcher", {"server.yaml": yaml, "prompt.md": _PROMPT})
    await service.install_from_repository(URL, [], [ServerValues("researcher")])


async def test_a_plugins_subagent_is_found_installed_and_listed(service, repo):  # noqa: F811
    await _install(service, repo)
    found = next(s for s in (await service.browse_repository(URL)).servers if s.name == "researcher")
    assert (found.subagent, found.transport, found.category) == ("researcher", "none", "assistant/agents")
    [installed] = await subagents.installed(service.store)
    assert (installed.prompt, installed.model, installed.tools) == (_PROMPT, "main", ("web_search", "web_extract"))
    prompt = await build_system_prompt(service.store, "owner", "", "")
    assert "# Subagents" in prompt and "- researcher: Researches a question across many web pages" in prompt
    # Turned off, it's neither listed nor handed tasks.
    await service.update_mcp_server("researcher", McpServerChanges(enabled=False))
    assert await subagents.installed(service.store) == []
    assert "# Subagents" not in await build_system_prompt(service.store, "owner", "", "")


async def test_a_task_for_it_runs_with_its_prompt_model_and_tools(service, script, repo, monkeypatch):  # noqa: F811
    await _install(service, repo)
    models: list[str] = []
    monkeypatch.setattr(subagent_module, "build_llm", lambda choice, model: models.append(model) or script.model())
    script.call("delegate", task="Who makes the best espresso machine?", agent="researcher")
    script.reply("La Marzocco, per three reviews.").reply("La Marzocco.")
    events = await collect(service.send(await service.session("owner", "cli"), "research espresso machines"))
    assert ToolFinished("delegate", "La Marzocco, per three reviews.") in events
    system = script.requests[1][0]
    assert isinstance(system, SystemMessage) and system.text.endswith(_PROMPT)
    assert system.text.startswith("You are a subagent of a personal assistant")
    assert {t.name for t in script.bound[1]} == {"web_search", "web_extract"}
    assert models == [service._model.model]


async def test_an_unknown_subagent_isnt_handed_the_task(service, script, repo):  # noqa: F811
    await _install(service, repo)
    script.call("delegate", task="x", agent="coder").reply("ok")
    events = await collect(service.send(await service.session("owner", "cli"), "go"))
    finished = next(e for e in events if isinstance(e, ToolFinished))
    assert finished.output == "Not delegated: No subagent named coder. The named ones: researcher."


async def test_a_subagent_section_needs_format_6_a_name_a_description_and_a_prompt_in_its_folder(service, repo):  # noqa: F811
    general = repo / "other" / "general"
    sections = {
        "old": _RESEARCHER.replace("format: 6", "format: 5"),
        "unnamed": _RESEARCHER.replace("  name: researcher\n", ""),
        "shouty": _RESEARCHER.replace("name: researcher", "name: Researcher"),
        "outside": _RESEARCHER.replace("prompt: prompt.md", "prompt: ../../../../etc/hosts"),
        "missing": _RESEARCHER.replace("prompt: prompt.md", "prompt: nope.md"),
        "tools": _RESEARCHER.replace("tools: [web_search, web_extract]", "tools: web_search"),
    }
    for name, yaml in sections.items():
        _write(general / name, {"server.yaml": yaml, "prompt.md": _PROMPT})
    problems = await _problems(service)
    assert "it brings a subagent, which needs format: 6" in problems
    assert "its subagent needs a name, a description and a prompt" in problems
    assert "its subagent name 'Researcher' must be a lowercase word" in problems
    assert "its subagent prompt '../../../../etc/hosts' isn't a file in its folder" in problems
    assert "its subagent prompt 'nope.md' isn't a file in its folder" in problems
    assert "its subagent's tools and plugins must be lists of names" in problems
