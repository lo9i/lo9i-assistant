"""Plain line-by-line REPL, used when input or output isn't a terminal (pipes, scripts)."""

import asyncio
from collections.abc import Awaitable, Callable

from assistant.core.attachments import Attachment
from assistant.core.events import ApprovalRequired
from assistant.client import DaemonClient
from assistant.core.agent import InvalidToken, Session
from assistant.gateways.cli.commands import help_lines
from assistant.gateways.cli.files import load_attachment
from assistant.gateways.cli.render import render
from assistant.gateways.cli.telegram_text import describe as describe_telegram
from assistant.gateways.cli.style import GREEN, RESET, YELLOW, code, paint

_HELP = "Commands:\n" + "\n".join(f"  {line}" for line in help_lines())

_USER_PROMPT = f"\n{paint(GREEN, '> ')}{code(GREEN)}"


class Repl:
    def __init__(self, service: DaemonClient, session: Session):
        self._service = service
        self._session = session
        self._attachments: list[Attachment] = []
        self._commands: dict[str, Callable[[str], Awaitable[None]]] = {
            "/help": self._help,
            "/new": self._new,
            "/attach": self._attach,
            "/telegram": self._telegram,
            "/": self._help,
        }

    async def loop(self) -> None:
        print(f"Thread {self._session.thread_id}. /help for commands.")
        while (line := await _read_line(_USER_PROMPT)) is not None and line != "/quit":
            if line or self._attachments:
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

    async def _telegram(self, arg: str) -> None:
        """/telegram shows status; /telegram <token> connects; /telegram pair or disconnect."""
        if arg == "disconnect":
            await self._service.disconnect_telegram()
        try:
            status = await self._telegram_action(arg)
        except InvalidToken as e:
            print(e)
            return
        text = describe_telegram(status, "")
        print(text.replace("Paste it below.", "Connect with: /telegram <token>") if not status.connected else text)

    async def _telegram_action(self, arg: str):
        if arg == "pair":
            return await self._service.start_telegram_pairing()
        if arg and arg != "disconnect":
            return await self._service.connect_telegram(arg)
        return await self._service.telegram_status()

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
