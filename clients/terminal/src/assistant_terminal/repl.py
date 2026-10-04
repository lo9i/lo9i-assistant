"""Plain line-by-line REPL, used when input or output isn't a terminal (pipes, scripts)."""

import asyncio
from collections.abc import Awaitable, Callable

from assistant.client import DaemonClient, DaemonUnavailableError
from assistant.client.files import load_attachment
from assistant.core.agent import InvalidNameError, Session
from assistant.core.attachments import Attachment
from assistant.core.events import ApprovalRequired, is_plugin_offer, is_question
from assistant_terminal.channels_text import NONE_INSTALLED
from assistant_terminal.channels_text import describe as describe_channel
from assistant_terminal.commands import GET_TO_KNOW_ME, help_lines
from assistant_terminal.conversations_text import when
from assistant_terminal.jobs_text import summary as jobs_summary
from assistant_terminal.mcp_text import shown as shown_servers
from assistant_terminal.mcp_text import summary as mcp_summary
from assistant_terminal.render import render
from assistant_terminal.sessions_text import describe as describe_sessions
from assistant_terminal.style import GREEN, RESET, YELLOW, code, paint
from assistant_terminal.usage_text import describe as describe_usage
from assistant_terminal.web_search_text import describe as describe_web_search

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
            "/channels": self._channels,
            "/email": self._email,
            "/mcp": self._mcp,
            "/startup": self._startup,
            "/model": self._model,
            "/audio": self._audio,
            "/websearch": self._web_search,
            "/skills": self._skills,
            "/plugins": self._plugins,
            "/name": self._name,
            "/get-to-know-me": self._get_to_know_me,
            "/jobs": self._jobs,
            "/usage": self._usage,
            "/profile": self._profile,
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

    async def _get_to_know_me(self, _: str) -> None:
        """In a conversation of its own."""
        await self._new("")
        await self._chat(GET_TO_KNOW_ME)

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

    async def _plugins(self, _: str) -> None:
        """Lists them; installing needs the full app (it asks for values)."""
        contents = await self._service.repositories.browse()
        listed = [*contents.servers, *contents.skills]
        print(
            "\n".join(f"{p.name}: {'installed' if p.installed else 'not installed'}. {p.description}" for p in listed)
        )

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
        days = int(arg) if arg.isdigit() else 7
        print(describe_usage(await self._service.usage.report(days), await self._service.usage.tokens(days)))

    async def _profile(self, _: str) -> None:
        """Shows it; editing needs the full app or the web app."""
        profile = (await self._service.memory.snapshot()).profile
        lines = [f"{name.replace('_', ' ').capitalize()}: {'; '.join(items)}" for name, items in profile.items()]
        print("\n".join(lines) or "The profile is empty.")

    async def _sessions(self, _: str) -> None:
        print(describe_sessions(await self._service.clients.list(), self._service.clients.own_id))

    async def _audio(self, _: str) -> None:
        status = await self._service.speech.settings()
        print(f"Voice messages: {status.model}, {status.decoding}, languages {', '.join(status.languages)}.")
        print(f"Spoken replies: {status.spoken_replies}, voice {status.voice}.")
        print("Change them with /audio in the full-screen app.")

    async def _model(self, _: str) -> None:
        status = await self._service.model.status()
        source = "set in the app" if status.source == "app" else "from .env"
        print(f"Model: {status.provider} ({source}), main {status.model}, worker {status.worker_model}.")
        print("Change it in the full-screen app with /model.")

    async def _startup(self, _: str) -> None:
        status = await self._service.system.startup_status()
        print(f"Start at boot is {'on' if status.enabled else 'off'}. Change it in the full-screen app with /startup.")

    async def _email(self, _: str) -> None:
        accounts = await self._service.email.accounts()
        if not accounts:
            print("No email account is connected. Set one up in the full-screen app with /email.")
        for account in accounts:
            default = " (default)" if account.default else ""
            print(f"Email: {account.label} <{account.sender}>{default} via {account.host}:{account.port}")
        if accounts:
            allowed = ", ".join(["your accounts", *await self._service.email.recipients()])
            print(f"Sends without asking to: {allowed}")

    async def _mcp(self, _: str) -> None:
        servers = shown_servers(await self._service.mcp.servers())
        for server in servers:
            print(mcp_summary(server))
        print(f"{'No MCP servers. Add' if not servers else 'Manage'} them in the full-screen app with /mcp.")

    async def _channels(self, _: str) -> None:
        """Status only: buttons (a new pairing code) are pressed in the full-screen app."""
        channels = await self._service.channels.list()
        print("\n\n".join(describe_channel(c) for c in channels) if channels else NONE_INSTALLED)

    async def _web_search(self, _: str) -> None:
        """Status only: the key is set in the full-screen app, so it never lands in the input history."""
        status = await self._service.web_search.status()
        text = describe_web_search(status, "")
        print(
            text.replace("Paste it below.", "Set it in the full-screen app with /websearch.")
            if not status.brave_key_set
            else text
        )

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
        if is_question(request):
            decisions[approval.interrupt_id] = await _answer_question(request)
            continue
        if is_plugin_offer(request):
            # Tokens are typed only in the install dialog, which the full app has.
            print(
                paint(
                    YELLOW, f"\nThe assistant offers {request.get('name')}. Install it with /plugins in the full app."
                )
            )
            decisions[approval.interrupt_id] = {"installed": False}
            continue
        print(paint(YELLOW, f"\nApprove {request.get('tool')} ({request.get('reason')}): {request.get('command')}"))
        answer = await _read_line("[y/N or reason to reject] ") or ""
        approved = answer.lower() in ("y", "yes")
        decisions[approval.interrupt_id] = {"approved": approved, "reason": None if approved else answer}
    return decisions


async def _answer_question(request: dict) -> dict:
    """Numbers of the options picked, separated by spaces; nothing skips."""
    options = list(request.get("options", []))
    print(paint(YELLOW, f"\n{request.get('question')}"))
    for number, option in enumerate(options, 1):
        print(f"  {number}. {option}")
    hint = "numbers, separated by spaces" if request.get("multiple") else "a number"
    answer = await _read_line(f"[{hint}, or Enter to skip] ") or ""
    numbers = {int(n) for n in answer.split() if n.isdigit()}
    picked = [o for i, o in enumerate(options, 1) if i in numbers]
    return {"choices": (picked if request.get("multiple") else picked[:1]) if answer else None}
