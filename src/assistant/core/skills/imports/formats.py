"""How a Claude Code skill or a Codex skill or prompt reads as one of the assistant's.

The header maps as it is: `name:` and `description:` (a prompt's name is its file's). What only a coding agent
understands is mapped or flagged: Claude Code's `${CLAUDE_SKILL_DIR}/` becomes a path relative to the skill's
folder, as the assistant's skills write them; placeholders for what the user typed after the command
(`$ARGUMENTS`, `$1`, a Codex prompt's `$FILE`) get a note saying they stand for what the user asked; and what
needs the agent's own tools (`allowed-tools:`, a subagent, `!` commands run as it loads, its tools named in the
text) is listed, so the user sees it works best handed to a coding agent."""

import re

from assistant.core.i18n import said
from assistant.core.skills import store

_DESCRIPTION_LIMIT = 200
_SKILL_DIR_PATH = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/")
_SKILL_DIR = re.compile(r"\$\{CLAUDE_SKILL_DIR\}")
_SKILL_ARGUMENTS = re.compile(r"\$(?:\{ARGUMENTS\}|ARGUMENTS\b|\d\b)")
_PROMPT_ARGUMENTS = re.compile(r"(?<!\$)\$(?:ARGUMENTS\b|[1-9]\b|[A-Z][A-Z0-9_]*\b)")
# Claude Code runs these as it loads the skill and puts their output in its place.
_LOAD_COMMAND = re.compile(r"!`[^`\n]+`")
# Tools only a coding agent has, named as tools: in backticks, as "<Tool> tool", or as Bash(git *).
_AGENT_TOOLS = "Bash|Read|Edit|MultiEdit|Write|Grep|Glob|Task|TodoWrite|NotebookEdit|WebFetch|WebSearch"
_TOOL_MENTION = re.compile(rf"`({_AGENT_TOOLS})`|\b({_AGENT_TOOLS})(?= tool\b|\()|\b(apply_patch|update_plan)\b")


def name(text: str) -> str:
    """A name the assistant's skills can have: lowercase letters, digits and hyphens. "" when nothing's left."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:63].rstrip("-")


def description(meta: dict, body: str) -> str:
    """The header's, or the first line of text when it has none, as Claude Code does."""
    given = str(meta.get("description") or "").strip()
    if given:
        return " ".join(given.split())
    lines = (line.strip().lstrip("#").strip() for line in body.splitlines())
    first = next((line for line in lines if line), "")
    return first[:_DESCRIPTION_LIMIT]


def skill_instructions(body: str, agent_name: str) -> str:
    """A skill's instructions as the assistant reads them."""
    text = _SKILL_DIR.sub("<this skill's folder>", _SKILL_DIR_PATH.sub("", body.strip()))
    return _with_arguments_note(text, _SKILL_ARGUMENTS, agent_name)


def prompt_instructions(body: str, meta: dict) -> str:
    """A Codex prompt's text as a skill's instructions: `$$` is a dollar sign there."""
    hint = str(meta.get("argument-hint") or "").strip()
    text = _with_arguments_note(body.strip(), _PROMPT_ARGUMENTS, "Codex", hint)
    return text.replace("$$", "$")


def needs_agent(meta: dict, body: str, agent_name: str) -> list[str]:
    """Why it works best handed to a coding agent; empty when the assistant can follow it as well."""
    reasons = [*_header_needs(meta, agent_name)]
    if _LOAD_COMMAND.search(body):
        reasons.append(said("It runs commands as {agent} loads it (!`…`); here they're only text.", agent=agent_name))
    tools = sorted({next(group for group in m.groups() if group) for m in _TOOL_MENTION.finditer(body)})
    if tools:
        reasons.append(said("It uses a coding agent's tools: {tools}.", tools=", ".join(tools)))
    return reasons


def problems(skill_name: str, instructions: str, files: list[str]) -> list[str]:
    """What stops it from being imported: a name the assistant can't use, or files it uses and doesn't have."""
    found = [] if store.valid_name(skill_name) else [said("Its name has no letters or digits to name a skill with.")]
    return [*found, *store.problems(instructions, files)]


def _header_needs(meta: dict, agent_name: str) -> list[str]:
    reasons = []
    tools = meta.get("allowed-tools") or meta.get("allowed_tools")
    if tools:
        listed = ", ".join(str(t) for t in tools) if isinstance(tools, list) else str(tools)
        reasons.append(said("Its header gives it {agent}'s tools: {tools}.", agent=agent_name, tools=listed))
    if meta.get("context") == "fork" or meta.get("agent"):
        reasons.append(said("It runs as a {agent} subagent.", agent=agent_name))
    if meta.get("hooks"):
        reasons.append(said("It sets {agent} hooks.", agent=agent_name))
    return reasons


def _with_arguments_note(text: str, placeholders: re.Pattern[str], agent_name: str, hint: str = "") -> str:
    used = sorted(set(placeholders.findall(text)))
    if not used:
        return text
    takes = f" It takes: {hint}." if hint else ""
    note = (
        f"(Written for {agent_name}, where {', '.join(used)} stand for what the user typed after the command: "
        f"take them from what the user asked.{takes})"
    )
    return f"{note}\n\n{text}"
