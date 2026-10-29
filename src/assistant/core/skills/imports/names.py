"""The name an imported skill gets here. One imported before keeps the name it got, so importing it again updates
it. Otherwise it takes its own name when no skill has it; when one does, that skill is never overwritten unless
the user said to replace it (and it's theirs, not built in or a plugin's): the import gets the agent's name added
instead, `pdf-claude`, then `pdf-claude-2`."""

from dataclasses import dataclass

from assistant.core.skills import store
from assistant.core.skills.imports.found import Found

_LONGEST = 63


@dataclass
class Names:
    # Every skill's name here, built-in ones too, and the names given in this import so far.
    taken: set[str]
    # Skills the user may have an import replace: theirs or the assistant's, not built in or a plugin's.
    replaceable: set[str]
    # The skills imported before, by the source's path.
    imported: dict[str, str]

    @classmethod
    def now(cls, imported: dict[str, str]) -> "Names":
        replaceable = {s.name for s in store.saved_skills() if not s.plugin}
        return cls({s.name for s in store.list_skills()}, replaceable, imported)

    def pick(self, item: Found, replace: bool = False) -> tuple[str, str]:
        """Its name and, when it isn't its own, why; marks the name taken."""
        name, why = self._pick(item, replace)
        self.taken.add(name)
        # Replaced once: a second import with that name in the same batch is renamed, not replacing the first.
        self.replaceable.discard(name)
        return name, why

    def preview(self, item: Found) -> tuple[str, str]:
        """What `pick` would give it now, without taking the name."""
        return self._pick(item, False)

    def _pick(self, item: Found, replace: bool) -> tuple[str, str]:
        if item.id in self.imported:
            return self.imported[item.id], ""
        if item.name not in self.taken:
            return item.name, ""
        if replace and item.name in self.replaceable:
            return item.name, f"replaces your skill {item.name}"
        renamed = self._suffixed(item.name, item.agent)
        return renamed, f"named {renamed}: you already have a skill named {item.name}"

    def _suffixed(self, name: str, agent: str) -> str:
        for n in range(1, len(self.taken) + 2):
            suffix = f"-{agent}" if n == 1 else f"-{agent}-{n}"
            candidate = f"{name[: _LONGEST - len(suffix)].rstrip('-')}{suffix}"
            if candidate not in self.taken:
                return candidate
        raise AssertionError("unreachable: more names tried than are taken")
