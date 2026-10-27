"""Plain line-by-line REPL, used when input or output isn't a terminal (pipes, scripts)."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

from assistant.client import DaemonClient, DaemonUnavailableError
from assistant.client.files import load_attachment
from assistant.core.agent import Agent, AgentFolders, HandoffError, InvalidNameError, Session, SkillError
from assistant.core.attachments import Attachment
from assistant.core.events import (
    ApprovalRequired,
    Dispatched,
    Event,
    is_plugin_offer,
    is_plugin_setup,
    is_question,
)
from assistant_terminal.channels_text import describe as describe_channel
from assistant_terminal.commands import GET_TO_KNOW_ME, agent_commands, help_lines
from assistant_terminal.conversations_text import listed_title, when
from assistant_terminal.jobs_text import summary as jobs_summary
from assistant_terminal.logs_text import log_line
from assistant_terminal.mcp_text import shown as shown_servers
from assistant_terminal.mcp_text import summary as mcp_summary
from assistant_terminal.notifications_text import notification_line
from assistant_terminal.plugins_text import checked_line, from_repositories, last_checked, source
from assistant_terminal.render import render
from assistant_terminal.sessions_text import describe as describe_sessions
from assistant_terminal.style import GREEN, RESET, YELLOW, code, paint
from assistant_terminal.usage_text import describe as describe_usage
from assistant_terminal.web_search_text import describe as describe_web_search

_USER_PROMPT = f"\n{paint(GREEN, '> ')}{code(GREEN)}"


class Repl:
    def __init__(self, service: DaemonClient, session: Session):
        self._service = service
        self._session = session
        # The REPL starts on the inbox (main.py); a message there goes where it belongs.
        self._inbox_id = session.thread_id
        self._attachments: list[Attachment] = []
        self._commands: dict[str, Callable[[str], Awaitable[None]]] = {
            "/help": self._help,
            "/new": self._new,
            "/inbox": self._inbox,
            "/move": self._move,
            "/conversations": self._conversations,
            "/notifications": self._notifications,
            "/attach": self._attach,
            "/mcp": self._mcp,
            "/startup": self._startup,
            "/host": self._host,
            "/model": self._model,
            "/audio": self._audio,
            "/websearch": self._web_search,
            "/skills": self._skills,
            "/plugins": self._plugins,
            "/name": self._name,
            "/pin": self._pin,
            "/unpin": self._unpin,
            "/get-to-know-me": self._get_to_know_me,
            "/jobs": self._jobs,
            "/usage": self._usage,
            "/logs": self._logs,
            "/profile": self._profile,
            "/sessions": self._sessions,
            "/": self._help,
        }

    async def loop(self) -> None:
        await self._conversations("")
        print("A message goes on in the conversation it's about, or starts one. /help for commands.")
        while (line := await _read_line(_USER_PROMPT)) is not None and line != "/quit":
            if line or self._attachments:
                await self._handle(line)

    async def _handle(self, line: str) -> None:
        name, _, arg = line.partition(" ")
        command = self._commands.get(name)
        if command:
            await command(arg.strip())
        elif agent := await self._agent(name):
            await self._hand(agent, arg.strip())
        else:
            await self._chat(line)

    async def _agent(self, name: str) -> Agent | None:
        """The installed plugin's agent this command switches to, like /claude."""
        if not name.startswith("/"):
            return None
        agents = await self._service.conversations.agents()
        offered = {c.name for c in agent_commands(agents)}
        return next((a for a in agents if f"/{a.command}" == name and name in offered), None)

    async def _hand(self, agent: Agent, arg: str) -> None:
        """`/claude <folder>` hands the conversation to the agent, `/claude off` back; alone it picks the folder."""
        if arg == "off":
            await self._service.conversations.take_back(self._session.thread_id)
            print("The assistant answers again from your next message.")
            return
        folder = arg or await _pick_folder(await self._service.conversations.agent_folders(), agent.name)
        if not folder:
            return
        if self._session.thread_id == self._inbox_id:
            await self._new("")  # the inbox sends every message on, so the agent gets a new conversation
        try:
            handoff = await self._service.conversations.hand_to(self._session.thread_id, agent.command, folder)
        except HandoffError as e:
            print(e)
            return
        print(f"{handoff.name} answers from your next message, working in {handoff.folder}.")

    async def _chat(self, text: str) -> None:
        attachments, self._attachments = self._attachments, []
        try:
            await self._run_turn(text, attachments)
        except DaemonUnavailableError as e:
            print(e)

    async def _run_turn(self, text: str, attachments: list[Attachment]) -> None:
        await self._turn(self._service.send(self._session, text, attachments))

    async def _turn(self, events: AsyncIterator[Event]) -> None:
        """Shows the run, then goes where the inbox sent its message on."""
        shown = await render(events)
        dispatched = shown.dispatched
        while shown.approvals:
            decisions = await _collect_decisions(shown.approvals)
            shown = await render(self._service.resume(self._session, decisions))
            dispatched = dispatched or shown.dispatched
        if dispatched is not None:
            await self._go_on(dispatched)

    async def _go_on(self, dispatched: Dispatched) -> None:
        """The inbox sent the message on: to the conversation it went to, or a new one, where it's sent. The
        next message goes there too; /inbox goes back."""
        if dispatched.thread_id:
            await self._service.resume_thread(self._session.user_id, dispatched.thread_id)
            self._session.thread_id = dispatched.thread_id
        else:
            self._session.thread_id = await self._service.new_thread(self._session.user_id)
        print(f"In {dispatched.title}. /inbox goes back.")
        if dispatched.carried:
            print(f"From the inbox:\n{dispatched.carried}")
        if dispatched.brief:
            print(f"Task for {dispatched.brief}:\n{dispatched.text}")
        await self._turn(self._service.send_dispatched(self._session, dispatched.id, dispatched.text, dispatched.brief))

    async def _get_to_know_me(self, _: str) -> None:
        """In a conversation of its own."""
        await self._new("")
        await self._chat(GET_TO_KNOW_ME)

    async def _help(self, _: str) -> None:
        extra = agent_commands(await self._service.conversations.agents())
        print("Commands:\n" + "\n".join(f"  {line}" for line in help_lines(extra)))

    async def _new(self, _: str) -> None:
        self._session.thread_id = await self._service.new_thread(self._session.user_id)
        print(f"New conversation {self._session.thread_id}. /inbox goes back.")

    async def _inbox(self, _: str) -> None:
        self._session.thread_id = self._inbox_id = await self._service.inbox_thread(self._session.user_id)
        print("In the inbox: the next message goes on where it belongs.")

    async def _move(self, _: str) -> None:
        """Asks in the inbox where the last message it sent on goes instead, and goes there."""
        await self._inbox("")
        await self._turn(self._service.move_dispatched(self._session))

    async def _notifications(self, arg: str) -> None:
        """/notifications lists them, numbered, newest first; /notifications <number> opens its conversation."""
        items = await self._service.notifications.list()
        if not arg.isdigit():
            print("\n".join(f"{i}. {notification_line(n)}" for i, n in enumerate(items, 1)) or "No notifications.")
            await self._service.notifications.mark_read()
            return
        index = int(arg) - 1
        if not 0 <= index < len(items) or not items[index].thread_id:
            print("No conversation to open for that number.")
            return
        await self._open(items[index].thread_id, items[index].title)

    async def _open(self, thread_id: str, title: str) -> None:
        await self._service.resume_thread(self._session.user_id, thread_id)
        self._session.thread_id = thread_id
        print(f"Opened: {title}")

    async def _conversations(self, arg: str) -> None:
        """/conversations lists them, numbered, newest first; /conversations <number> opens one."""
        items = await self._service.conversations.recent()
        if not arg.isdigit():
            lines = [f"{i}. {listed_title(c)} ({when(c)})" for i, c in enumerate(items, 1)]
            print("\n".join(lines) or "No conversations yet.")
            return
        index = int(arg) - 1
        if not 0 <= index < len(items):
            print("No conversation with that number.")
            return
        await self._open(items[index].thread_id, listed_title(items[index]))

    async def _plugins(self, _: str) -> None:
        """Lists them, the installed channels' setup and the email accounts; installing, pressing a
        channel's buttons and connecting an account need the full app (they ask for values)."""
        read = await self._service.repositories.plugins(cached=True)
        found, unread = from_repositories(read)
        if checked := last_checked(read):
            print(f"As the repositories offered them when last checked ({_checked(checked)}).")
        print(
            "\n".join(
                f"{p.name} ({source(p)}): {'installed' if p.installed else 'not installed'}. {p.description}"
                for p in found
            )
        )
        print("\n".join(unread))
        channels = await self._service.channels.list()
        if channels:
            print("\n\n".join(describe_channel(c) for c in channels))
        await self._email()

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

    async def _pin(self, arg: str) -> None:
        thread_id = self._session.thread_id
        if not arg:
            pinned = await self._service.conversations.pinned(thread_id)
            print(f"Pinned: {', '.join(pinned)}." if pinned else "No skills pinned: /pin <skill>.")
            return
        try:
            await self._service.conversations.pin(thread_id, arg)
        except SkillError as e:
            print(e)
            return
        print(f"Pinned {arg} to this conversation, from your next message.")

    async def _unpin(self, arg: str) -> None:
        if not arg:
            print("Which skill? /unpin <skill>.")
            return
        await self._service.conversations.unpin(self._session.thread_id, arg)
        print(f"Unpinned {arg}, from your next message.")

    async def _jobs(self, _: str) -> None:
        jobs = await self._service.jobs.list()
        print("\n".join(f"{j.name}: {jobs_summary(j)}" for j in jobs) or "No scheduled jobs.")

    async def _usage(self, arg: str) -> None:
        days = int(arg) if arg.isdigit() else 7
        print(describe_usage(await self._service.usage.report(days), await self._service.usage.tokens(days)))

    async def _logs(self, arg: str) -> None:
        """The latest entries of the daemon's log; following it needs the full app or the web app."""
        page = await self._service.logs.page("daemon", lines=int(arg) if arg.isdigit() else 50)
        print("\n".join(log_line(e) for e in page.entries) or "Nothing logged yet.")

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

    async def _host(self, _: str) -> None:
        host = await self._service.system.host()
        print(f"{host.hostname}: {host.os} {host.arch}, lo9i v{host.version}. More in the full-screen app with /host.")

    async def _email(self) -> None:
        accounts = await self._service.email.accounts()
        if not accounts:
            print("No email account is connected. Set one up in the full-screen app, in /plugins.")
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
        if is_plugin_setup(request):
            print(paint(YELLOW, f"\nSet up {request.get('name')} in /plugins in the full app."))
            decisions[approval.interrupt_id] = {"done": True}
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


async def _pick_folder(folders: AgentFolders, agent_name: str) -> str | None:
    """The workspace or a folder used before by its number, or a full path; nothing cancels."""
    offered = [folders.workspace, *folders.recent]
    print(paint(YELLOW, f"\nWhere should {agent_name} work?"))
    for number, folder in enumerate(offered, 1):
        print(f"  {number}. {folder}" + (" (workspace)" if number == 1 else ""))
    answer = (await _read_line("[a number or a full path, or Enter to cancel] ") or "").strip()
    if answer.isdigit() and 1 <= int(answer) <= len(offered):
        return offered[int(answer) - 1]
    return answer or None


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


def _checked(checked: str) -> str:
    return checked_line(checked, checking=False, failed=False, now=datetime.now(UTC)).lower()
