"""The assistant's own tools most conversations never use (email, jobs, skill writing) load on demand, like a
plugin's: listed by group in the system prompt, offered once a conversation loads the group."""

from typing import Any

from assistant.core.events import ToolFinished
from assistant.core.plugin_loading import LOAD_TOOLS
from assistant.core.tools.registry import offered_tools, tool_groups
from tests.conftest import collect


def _names(bound: list[Any]) -> set[str]:
    return {t["function"]["name"] if isinstance(t, dict) else t.name for t in bound}


def test_the_groups_and_what_every_request_offers():
    groups = {group: sorted(t.name for t in tools) for group, tools in tool_groups(["email", "jobs", "skills"]).items()}
    assert groups == {
        "email": ["read_email", "search_email", "send_email", "set_up_email"],
        "jobs": ["delete_job", "list_jobs", "schedule_job", "update_job"],
        "skill-writing": ["delete_skill", "import_skills", "list_importable_skills", "save_skill"],
    }
    assert {"use_skill", "offer_plugin"} <= {t.name for t in offered_tools(["skills"])}


async def test_a_group_is_listed_then_loaded_for_the_rest_of_the_epoch(service, script):
    script.call(LOAD_TOOLS, plugin="jobs").reply("Loaded.").reply("And again.")
    session = await service.session("owner", "cli")
    await collect(service.send(session, "remind me every morning"))
    await collect(service.send(session, "and on weekends"))
    first, loaded, later = (_names(b) for b in script.bound)
    assert "schedule_job" not in first and "send_email" not in first and LOAD_TOOLS in first
    assert {"schedule_job", "list_jobs", "update_job", "delete_job"} <= loaded and "schedule_job" in later
    assert "- jobs: delete_job, list_jobs, schedule_job, update_job" in script.requests[0][0].text


async def test_calling_a_group_tool_not_loaded_runs_it_and_loads_the_group(service, script):
    script.call("list_jobs").reply("None.")
    session = await service.session("owner", "cli")
    events = await collect(service.send(session, "my jobs?"))
    assert any(isinstance(e, ToolFinished) and e.name == "list_jobs" for e in events)
    assert "list_jobs" in _names(script.bound[1])
