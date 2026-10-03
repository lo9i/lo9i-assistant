"""Plain line-by-line REPL, used when input or output isn't a terminal (pipes, scripts)."""

import asyncio
from collections.abc import Awaitable, Callable

from assistant.client import DaemonClient, DaemonUnavailableError
from assistant.client.files import load_attachment
from assistant.core.agent import InvalidNameError, InvalidTokenError, Session
from assistant.core.attachments import Attachment
from assistant.core.events import ApprovalRequired
from assistant_terminal.commands import help_lines
from assistant_terminal.conversations_text import when
from assistant_terminal.jobs_text import summary as jobs_summary
from assistant_terminal.mcp_text import summary as mcp_summary
from assistant_terminal.render import render
from assistant_terminal.sessions_text import describe as describe_sessions
from assistant_terminal.slack_text import describe as describe_slack
from assistant_terminal.style import GREEN, RESET, YELLOW, code, paint
from assistant_terminal.telegram_text import describe as describe_telegram
from assistant_terminal.usage_text import describe as describe_usage

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
            "/conversations": self._conversations,
            "/attach": self._attach,
            "/telegram": self._telegram,
            "/slack": self._slack,
            "/email": self._email,
            "/mcp": self._mcp,
            "/startup": self._startup,
            "/skills": self._skills,
            "/name": self._name,
            "/jobs": self._jobs,
            "/usage": self._usage,
            "/sessions": self._sessions,
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
        try:
            await self._run_turn(text, attachments)
        except DaemonUnavailableError as e:
            print(e)

    async def _run_turn(self, text: str, attachments: list[Attachment]) -> None:
        approvals = await render(self._service.send(self._session, text, attachments))
        while approvals:
            decisions = await _collect_decisions(approvals)
            approvals = await render(self._service.resume(self._session, decisions))

    async def _help(self, _: str) -> None:
        print(_HELP)

    async def _new(self, _: str) -> None:
        self._session.thread_id = await self._service.new_thread(self._session.user_id)
        print(f"New thread {self._session.thread_id}.")

    async def _conversations(self, arg: str) -> None:
        """/conversations lists them, numbered; /conversations <number> resumes one."""
        items = await self._service.conversations.recent()
        if not arg.isdigit():
            lines = [f"{i}. {c.title} ({when(c)})" for i, c in enumerate(items, 1)]
            print("\n".join(lines) or "No earlier conversations yet.")
            return
        index = int(arg) - 1
        if not 0 <= index < len(items):
            print("No conversation with that number.")
            return
        await self._service.resume_thread(self._session.user_id, items[index].thread_id)
        self._session.thread_id = items[index].thread_id
        print(f"Resumed: {items[index].title}")

    async def _skills(self, _: str) -> None:
        skills = await self._service.skills.list()
        print("\n".join(f"{s.name}: {s.description}" for s in skills) or "No skills yet.")

    async def _name(self, arg: str) -> None:
        if not arg:
            print(await self._service.identity.name() or "The assistant has no name yet: /name <name>.")
            return
        try:
            print(f"Renamed to {await self._service.identity.rename(arg)}.")
        except InvalidNameError as e:
            print(e)

    async def _jobs(self, _: str) -> None:
        jobs = await self._service.jobs.list()
        print("\n".join(f"{j.name}: {jobs_summary(j)}" for j in jobs) or "No scheduled jobs.")

    async def _usage(self, arg: str) -> None:
        print(describe_usage(await self._service.usage.report(int(arg) if arg.isdigit() else 7)))

    async def _sessions(self, _: str) -> None:
        print(describe_sessions(await self._service.clients.list(), self._service.clients.own_id))

    async def _startup(self, _: str) -> None:
        status = await self._service.system.startup_status()
        print(f"Start at boot is {'on' if status.enabled else 'off'}. Change it in the full-screen app with /startup.")

    async def _email(self, _: str) -> None:
        status = await self._service.email.status()
        if status.connected:
            allowed = ", ".join(status.allowed_recipients) or "(only you)"
            print(f"Email: {status.sender} via {status.host}:{status.port}. Allowed: {allowed}")
        else:
            print("Email isn't connected. Set it up in the full-screen app with /email.")

    async def _mcp(self, _: str) -> None:
        servers = await self._service.mcp.servers()
        for server in servers:
            print(mcp_summary(server))
        print(f"{'No MCP servers. Add' if not servers else 'Manage'} them in the full-screen app with /mcp.")

    async def _slack(self, _: str) -> None:
        status = await self._service.slack.status()
        if status.connected:
            print(describe_slack(status, ""))
        else:
            print("Slack isn't connected. Set it up in the full-screen app with /slack.")

    async def _telegram(self, arg: str) -> None:
        """/telegram shows status; /telegram <token> connects; /telegram pair or disconnect."""
        if arg == "disconnect":
            await self._service.telegram.disconnect()
        try:
            status = await self._telegram_action(arg)
        except InvalidTokenError as e:
            print(e)
            return
        text = describe_telegram(status, "")
        print(text.replace("Paste it below.", "Connect with: /telegram <token>") if not status.connected else text)

    async def _telegram_action(self, arg: str):
        if arg == "pair":
            return await self._service.telegram.start_pairing()
        if arg and arg != "disconnect":
            return await self._service.telegram.connect(arg)
        return await self._service.telegram.status()

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
