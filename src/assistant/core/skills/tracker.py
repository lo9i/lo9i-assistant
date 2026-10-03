"""Records skill scripts that fail, through LangChain callbacks like the usage tracker, so neither
bash nor the skills need to know about it. A bash command that uses a file in a skill's folder
counts for that skill: a non-zero exit code or a timeout is a failure, exit code 0 clears them."""

from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from assistant.core.health import HealthLog
from assistant.core.skills.store import skill_in


class SkillScriptTracker(AsyncCallbackHandler):
    def __init__(self, health: HealthLog) -> None:
        self._health = health
        # The skill each running bash call uses.
        self._running: dict[UUID, str] = {}

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name") or kwargs.get("name", "")
        skill = skill_in(str((inputs or {}).get("command", ""))) if name == "bash" else None
        if skill is not None:
            self._running[run_id] = skill

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        skill = self._running.pop(run_id, None)
        artifact = getattr(output, "artifact", None)
        # No artifact: the command didn't run (the user rejected it).
        if skill is None or not isinstance(artifact, dict):
            return
        if artifact.get("exit_code") == 0:
            await self._health.succeeded("skill", skill)
        else:
            await self._health.failed("skill", skill, str(getattr(output, "content", output)))

    async def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._running.pop(run_id, None)
