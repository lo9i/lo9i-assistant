"""What the sidebar shows besides its pages, read from the daemon (nav.py's `NavState`): the conversations open here and
any other working, and the counts the web app's sidebar shows beside its pages."""

from assistant.client.daemon_client import DaemonClient
from assistant_terminal.nav import CHAT, SETTINGS, NavState
from assistant_terminal.open_text import OpenItem, open_list


async def read_open(service: DaemonClient, opened: list[str], current: str, inbox: str) -> list[OpenItem]:
    """The conversations opened here, in order, then any other with a reply or a coding task running (open_text.py)."""
    conversations = await service.conversations.recent()
    runs = await service.runs_in_progress()
    tasks = await service.tasks.running()
    working = {r["thread_id"] for r in runs} | {task.thread_id for task in tasks if task.thread_id}
    waiting = {i for i in opened if await service.conversations.pending_approvals(i)}
    return open_list(opened, current, inbox, conversations, working, waiting)


async def read_nav(service: DaemonClient, opened: list[str], current: str, inbox: str) -> NavState:
    items = await read_open(service, opened, current, inbox)
    counts = {
        CHAT: sum(item.waiting for item in items),
        "subagents": sum(s.status in ("running", "waiting") for s in await service.subagents.list()),
        "notifications": sum(not n.read for n in await service.notifications.list()),
        "alerts": len(await service.alerts.list()),
        SETTINGS: len(await service.repositories.updates()),
    }
    return NavState(tuple(items), counts)
