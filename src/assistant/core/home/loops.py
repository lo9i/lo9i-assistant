"""Home's Open loops card, built by code (core/home/coded.py): what's still to do or waiting (core/proactive/loops.py),
but bills due, which the Expenses card shows. The web app draws it live from the loops, with buttons to open each
one's conversation and mark it done; this result is what the other apps show (the terminal app's /home)."""

from langgraph.store.base import BaseStore

from assistant.core import i18n
from assistant.core.home.model import HomeItem, SectionContent
from assistant.core.proactive import loops
from assistant.core.proactive.model import OpenLoop

# The kind of the loops the expenses plugin's list for the day keeps (and a conversation's payment due): left out.
BILL_DUE = "bill due"


def shown(found: list[OpenLoop]) -> list[OpenLoop]:
    """The open ones but bills: those with a due day first, the soonest first, then the rest as given (newest
    first)."""
    listed = [o for o in found if o.status == "open" and o.kind != BILL_DUE]
    return sorted((o for o in listed if o.due), key=lambda o: o.due) + [o for o in listed if not o.due]


class LoopsSection:
    def __init__(self, store: BaseStore, user_id: str) -> None:
        self._store = store
        self._user_id = user_id

    async def build(self) -> SectionContent:
        """In the language chosen when it's built."""
        t, found = await i18n.chosen(self._store), shown(await loops.open_loops(self._store, self._user_id))
        if not found:
            return SectionContent(items=[], note=t("Nothing open."))
        return SectionContent(items=[HomeItem(title=o.text, date=o.due) for o in found])
