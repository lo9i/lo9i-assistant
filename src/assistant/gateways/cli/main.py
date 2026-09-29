"""CLI gateway: a REPL over AssistantService."""

import asyncio
import json
import mimetypes
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from assistant.core.attachments import Attachment
from assistant.core.config import settings
from assistant.core.events import ApprovalRequired, Done, Error, Event, TextDelta, ToolFinished, ToolStarted
from assistant.core.service import AssistantService, Session

_HELP = """Commands:
  /attach <path>   attach a file to the next message
  /new             start a new conversation
  /quit            exit"""

_PREVIEW_CHARS = 500


class _Repl:
    def __init__(self, service: AssistantService, session: Session):
        self._service = service
        self._session = session
        self._attachments: list[Attachment] = []
        self._commands: dict[str, Callable[[str], Awaitable[None]]] = {
            "/help": self._help,
            "/new": self._new,
            "/attach": self._attach,
        }

    async def loop(self) -> None:
        print(f"Thread {self._session.thread_id}. /help for commands.")
        while (line := await _read_line("\n> ")) is not None and line != "/quit":
            if line:
                await self._handle(line)

    async def _handle(self, line: str) -> None:
        name, _, arg = line.partition(" ")
        command = self._commands.get(name)
        if command:
            await command(arg.strip())
        else:
            await self._chat(line)

    async def _chat(self, text: str) -> None:
        attachments, self._attachments = self._attachments, []
        approvals = await _render(self._service.send(self._session, text, attachments))
        while approvals:
            decisions = await _collect_decisions(approvals)
            approvals = await _render(self._service.resume(self._session, decisions))

    async def _help(self, _: str) -> None:
        print(_HELP)

    async def _new(self, _: str) -> None:
        self._session.thread_id = await self._service.new_thread(self._session.user_id)
        print(f"New thread {self._session.thread_id}.")

    async def _attach(self, arg: str) -> None:
        path = Path(arg).expanduser()
        if not path.is_file():
            print(f"No such file: {path}")
            return
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._attachments.append(Attachment(name=path.name, media_type=media_type, data=path.read_bytes()))
        print(f"Attached {path.name} ({media_type}).")


async def _read_line(prompt: str) -> str | None:
    try:
        return (await asyncio.to_thread(input, prompt)).strip()
    except (EOFError, KeyboardInterrupt):
        return None


async def _render(events: AsyncIterator[Event]) -> list[ApprovalRequired]:
    """Print events and return the approvals the run is waiting on."""
    approvals: list[ApprovalRequired] = []
    async for event in events:
        if isinstance(event, ApprovalRequired):
            approvals.append(event)
        else:
            _print_event(event)
    return approvals


def _print_event(event: Event) -> None:
    match event:
        case TextDelta(text):
            print(text, end="", flush=True)
        case ToolStarted(name, args):
            print(f"\n[{name}] {json.dumps(args)}")
        case ToolFinished(name, output):
            print(f"[{name} result]\n{_preview(output)}")
        case Error(message):
            print(f"\n[error] {message}")
        case Done():
            print()


def _preview(output: str) -> str:
    return output if len(output) < _PREVIEW_CHARS else output[:_PREVIEW_CHARS] + " ..."


async def _collect_decisions(approvals: list[ApprovalRequired]) -> dict[str, dict]:
    decisions = {}
    for approval in approvals:
        request = approval.request
        print(f"\nApprove {request.get('tool')} ({request.get('reason')}): {request.get('command')}")
        answer = await _read_line("[y/N or reason to reject] ") or ""
        approved = answer.lower() in ("y", "yes")
        decisions[approval.interrupt_id] = {"approved": approved, "reason": None if approved else answer}
    return decisions


async def _main() -> None:
    async with AssistantService.open() as service:
        session = await service.session(settings.owner_id, "cli")
        await _Repl(service, session).loop()


def run() -> None:
    asyncio.run(_main())
