"""Plain line-by-line REPL, used when input or output isn't a terminal (pipes, scripts)."""

import asyncio
from collections.abc import Awaitable, Callable

from assistant.core.attachments import Attachment
from assistant.core.events import ApprovalRequired
from assistant.core.agent import AssistantService, Session
from assistant.gateways.cli.files import load_attachment
from assistant.gateways.cli.render import render
from assistant.gateways.cli.style import GREEN, RESET, YELLOW, code, paint

_HELP = """Commands:
  /attach <path>   attach a file to the next message
  /new             start a new conversation
  /quit            exit"""

_USER_PROMPT = f"\n{paint(GREEN, '> ')}{code(GREEN)}"


class Repl:
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
        while (line := await _read_line(_USER_PROMPT)) is not None and line != "/quit":
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
        approvals = await render(self._service.send(self._session, text, attachments))
        while approvals:
            decisions = await _collect_decisions(approvals)
            approvals = await render(self._service.resume(self._session, decisions))

    async def _help(self, _: str) -> None:
        print(_HELP)

    async def _new(self, _: str) -> None:
        self._session.thread_id = await self._service.new_thread(self._session.user_id)
        print(f"New thread {self._session.thread_id}.")

    async def _attach(self, arg: str) -> None:
        try:
            attachment = load_attachment(arg)
        except FileNotFoundError as e:
            print(e)
            return
        self._attachments.append(attachment)
        print(f"Attached {attachment.name} ({attachment.media_type}).")


async def _read_line(prompt: str) -> str | None:
    try:
        return (await asyncio.to_thread(input, prompt)).strip()
    except (EOFError, KeyboardInterrupt):
        return None
    finally:
        print(code(RESET), end="", flush=True)


async def _collect_decisions(approvals: list[ApprovalRequired]) -> dict[str, dict]:
    decisions = {}
    for approval in approvals:
        request = approval.request
        print(paint(YELLOW, f"\nApprove {request.get('tool')} ({request.get('reason')}): {request.get('command')}"))
        answer = await _read_line("[y/N or reason to reject] ") or ""
        approved = answer.lower() in ("y", "yes")
        decisions[approval.interrupt_id] = {"approved": approved, "reason": None if approved else answer}
    return decisions
