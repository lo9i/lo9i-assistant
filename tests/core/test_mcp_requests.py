"""What an MCP server asks during a call (core/mcp/asking.py, answers.py): a form the user fills in or a link to open,
shown like an approval, which pauses the run; text from the model, approved first on a server that isn't trusted, at
most so much and so often. On the 2026-07-28 protocol and on an older one. And the tools lo9i adds for a server's
resources and prompts (core/mcp/listings.py), off until the user turns them on. The server runs in-process."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any

import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver import Elicit, ElicitationResult, Resolve, Sample
from mcp.types import (
    CreateMessageResult,
    ElicitRequestFormParams,
    ElicitRequestURLParams,
    ElicitResult,
    SamplingMessage,
    TextContent,
)
from pydantic import BaseModel

from assistant.core.agent import AssistantService, McpServer, McpServerChanges, Session
from assistant.core.events import ApprovalRequired, TextDelta, ToolFinished
from assistant.core.mcp import elicitation
from assistant.core.mcp import hub as hub_module
from assistant.core.mcp import sampling as sampling_module
from tests.conftest import collect

ORDER = "mcp__shop__order"
SUMMARY = "mcp__shop__summary"


class Size(BaseModel):
    size: str
    count: int = 1
    gift: bool = False


def _ask_size() -> Elicit[Size]:
    return Elicit("Which size?", Size)


def _ask_summary() -> Sample:
    message = SamplingMessage(role="user", content=TextContent(type="text", text="Summarize the shop"))
    return Sample([message], max_tokens=5000, system_prompt="Be brief.")


def _shop_server() -> MCPServer:
    server = MCPServer("shop")

    @server.tool()
    def order(picked: Annotated[ElicitationResult[Size], Resolve(_ask_size)]) -> str:
        """Order a shirt."""
        if picked.action != "accept":
            return f"no order ({picked.action})"
        return f"ordered {picked.data.count} {picked.data.size}{' as a gift' if picked.data.gift else ''}"

    @server.tool()
    def summary(text: Annotated[CreateMessageResult, Resolve(_ask_summary)]) -> str:
        """Summarize the shop."""
        assert isinstance(text.content, TextContent)
        return f"summary: {text.content.text}"

    @server.resource("shop://catalog", mime_type="text/plain")
    def catalog() -> str:
        """What the shop sells."""
        return "shirts, hats"

    @server.prompt()
    def welcome(name: str) -> str:
        """Welcome a customer."""
        return f"Welcome {name} to the shop."

    return server


@pytest.fixture(params=["auto", "legacy"])
def mode(request) -> str:
    """The 2026-07-28 protocol, where the server asks in its answer, and an older one, where it asks mid-call."""
    return request.param


@pytest.fixture
async def service(script, digests, summaries, titles, monkeypatch, mode) -> AsyncIterator[AssistantService]:
    fake = _shop_server()

    def connect(server, handler, auth, extensions, in_flight=None):
        asked: dict[str, Any] = {}
        if in_flight is not None:
            asked = {"elicitation_callback": in_flight.elicit, "sampling_callback": in_flight.sample}
        return Client(fake, message_handler=handler, extensions=extensions, mode=mode, **asked)

    monkeypatch.setattr(hub_module, "open_client", connect)
    async with AssistantService.open() as svc:
        stop = asyncio.Event()
        task = asyncio.create_task(svc.mcp.run(stop))
        yield svc
        stop.set()
        await task


@pytest.fixture
def sampled(script, monkeypatch) -> list[int | None]:
    """The model servers' text comes from: the script, recording the most it may write each time."""
    limits: list[int | None] = []

    def build(choice, model, max_tokens=None):
        limits.append(max_tokens)
        return script.model()

    monkeypatch.setattr(sampling_module, "build_llm", build)
    return limits


async def _add(service: AssistantService, **fields: Any) -> None:
    await service.add_mcp_server(McpServer(name="shop", command="shop-server", **fields))
    for _ in range(100):
        if (await service.mcp_servers())[0].status == "connected":
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("the server never connected")


async def _form(service: AssistantService, session: Session, text: str) -> ApprovalRequired:
    events = await collect(service.send(session, text))
    return next(e for e in events if isinstance(e, ApprovalRequired))


async def test_a_servers_form_pauses_the_run_and_the_answer_goes_to_the_server(service, script):
    await _add(service, trusted=True)
    script.call(ORDER).reply("ordered")
    session = await service.session("owner", "web")
    form = await _form(service, session, "order a shirt")
    assert form.request["kind"] == "form" and form.request["asked_by"] == "shop"
    assert form.request["message"] == "Which size?"
    assert [(f["key"], f["type"], f["required"]) for f in form.request["fields"]] == [
        ("size", "text", True),
        ("count", "integer", False),
        ("gift", "boolean", False),
    ]
    answer = {"action": "accept", "content": {"size": "M", "count": "2", "gift": True}}
    events = await collect(service.resume(session, {form.interrupt_id: answer}))
    assert ToolFinished(ORDER, "ordered 2 M as a gift") in events


async def test_a_declined_form_is_told_to_the_server_and_a_new_message_declines_it(service, script):
    await _add(service, trusted=True)
    script.call(ORDER).reply("ok")
    session = await service.session("owner", "web")
    form = await _form(service, session, "order a shirt")
    events = await collect(service.resume(session, {form.interrupt_id: {"action": "decline"}}))
    assert ToolFinished(ORDER, "no order (decline)") in events
    script.call(ORDER).reply("ok").reply("fine")
    await _form(service, session, "order another")
    events = await collect(service.send(session, "never mind"))
    assert ToolFinished(ORDER, "no order (decline)") in events


async def test_a_form_missing_a_required_field_is_cancelled(service, script):
    await _add(service, trusted=True)
    script.call(ORDER).reply("ok")
    session = await service.session("owner", "web")
    form = await _form(service, session, "order a shirt")
    events = await collect(service.resume(session, {form.interrupt_id: {"action": "accept", "content": {"count": 3}}}))
    assert ToolFinished(ORDER, "no order (cancel)") in events


async def test_nobody_is_asked_in_a_scheduled_run(service, script):
    await _add(service, trusted=True)
    script.call(ORDER).reply("couldn't")
    events = await collect(service.send(Session("owner", "worker", "job:a:1"), "order a shirt"))
    assert not any(isinstance(e, ApprovalRequired) for e in events)
    assert ToolFinished(ORDER, "no order (decline)") in events


async def test_text_a_server_asks_the_model_for_is_approved_first_and_never_shown_as_the_reply(
    service, script, sampled
):
    await _add(service)
    script.call(SUMMARY).reply("SAMPLED TEXT").reply("done")
    session = await service.session("owner", "web")
    tool = await _form(service, session, "summarize the shop")
    assert tool.request["tool"] == SUMMARY  # a tool of a server that isn't trusted is approved first, as always
    events = await collect(service.resume(session, {tool.interrupt_id: {"approved": True}}))
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    assert approval.request["tool"] == "shop (sampling)" and "Summarize the shop" in approval.request["command"]
    assert "[system] Be brief." in approval.request["command"]
    events = await collect(service.resume(session, {approval.interrupt_id: {"approved": True}}))
    assert ToolFinished(SUMMARY, "summary: SAMPLED TEXT") in events
    assert TextDelta("SAMPLED TEXT") not in events
    assert sampled == [sampling_module.MAX_TOKENS]
    sent = script.requests[-2]
    assert [m.type for m in sent] == ["system", "human"] and sent[-1].text == "Summarize the shop"


async def test_a_trusted_server_gets_text_without_asking_and_a_rejected_one_gets_none(service, script, sampled):
    await _add(service, trusted=True)
    script.call(SUMMARY).reply("TEXT").reply("done")
    events = await collect(service.send(await service.session("owner", "web"), "summarize"))
    assert ToolFinished(SUMMARY, "summary: TEXT") in events
    await service.update_mcp_server("shop", McpServerChanges(trusted=False))
    script.call(SUMMARY).reply("done")
    session = await service.session("owner", "web")
    tool = await _form(service, session, "summarize again")
    events = await collect(service.resume(session, {tool.interrupt_id: {"approved": True}}))
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    events = await collect(service.resume(session, {approval.interrupt_id: {"approved": False, "reason": "no"}}))
    finished = next(e for e in events if isinstance(e, ToolFinished))
    assert finished.output.startswith("Error from shop") and "rejected" in finished.output


async def test_a_server_gets_text_only_so_often(service, script, sampled, monkeypatch):
    monkeypatch.setattr(sampling_module, "SAMPLES_PER_HOUR", 1)
    await _add(service, trusted=True)
    script.call(SUMMARY).reply("TEXT").reply("done").call(SUMMARY).reply("done")
    session = await service.session("owner", "web")
    await collect(service.send(session, "summarize"))
    events = await collect(service.send(session, "summarize again"))
    finished = next(e for e in events if isinstance(e, ToolFinished))
    assert "in the last hour" in finished.output and len(sampled) == 1


async def test_resources_and_prompts_get_tools_once_turned_on(service, script):
    await _add(service, trusted=True)
    [status] = await service.mcp_servers()
    assert status.offers == ["prompts", "resources"] and not status.resources and not status.prompts
    assert {t.name for t in status.tools} == {"order", "summary"}
    assert service.mcp.tool("mcp__shop__list_resources") is None
    await service.update_mcp_server("shop", McpServerChanges(resources=True, prompts=True))
    script.call("mcp__shop__list_resources").call("mcp__shop__read_resource", uri="shop://catalog")
    script.call("mcp__shop__get_prompt", name="welcome", arguments={"name": "Ana"}).reply("done")
    events = await collect(service.send(await service.session("owner", "web"), "what does the shop sell?"))
    outputs = [e.output for e in events if isinstance(e, ToolFinished)]
    assert outputs[0].startswith("- shop://catalog (text/plain): catalog — What the shop sells.")
    assert outputs[1] == "shirts, hats"
    assert "Welcome Ana to the shop." in outputs[2]
    assert service.mcp.tool("mcp__shop__read_resource").read_only  # subagents and Home get it too


def test_a_forms_choices_and_a_link_are_shown_and_answered_as_their_types():
    schema = {
        "type": "object",
        "properties": {
            "color": {"type": "string", "enum": ["r", "g"], "enumNames": ["Red", "Green"]},
            "plan": {"type": "string", "oneOf": [{"const": "pro", "title": "Pro"}]},
            "tags": {"type": "array", "items": {"enum": ["a", "b"]}},
            "email": {"type": "string", "format": "email", "description": "Where to write"},
            "price": {"type": "number", "default": 2.5},
        },
        "required": ["color"],
    }
    form = elicitation.request("shop", ElicitRequestFormParams(message="Pick", requested_schema=schema))
    assert form is not None
    fields = {f["key"]: f for f in form["fields"]}
    assert fields["color"]["options"] == [{"value": "r", "label": "Red"}, {"value": "g", "label": "Green"}]
    assert fields["plan"]["type"] == "choice" and fields["tags"]["type"] == "choices"
    assert fields["email"]["format"] == "email" and fields["price"]["default"] == 2.5
    given = {"color": "g", "tags": ["b", "z"], "price": "3", "plan": "basic"}
    assert elicitation.result(form, {"action": "accept", "content": given}).content == {
        "color": "g",
        "tags": ["b"],
        "price": 3.0,
    }
    assert elicitation.result(form, {"action": "accept", "content": {"color": "blue"}}).action == "cancel"
    link = elicitation.request(
        "shop", ElicitRequestURLParams(message="Pay", url="https://pay.example", elicitation_id="1")
    )
    assert link is not None and link["url"] == "https://pay.example"
    assert elicitation.result(link, {"action": "accept"}) == ElicitResult(action="accept")
    bad = ElicitRequestURLParams(message="Run", url="file:///etc/passwd", elicitation_id="2")
    assert elicitation.request("shop", bad) is None
