"""Skills other coding agents keep on this computer (Claude Code, Codex), copied into the assistant's own.

Where they are (`places.py`): Claude Code's `~/.claude/skills/` and a project's `.claude/skills/`, Codex's
`~/.codex/skills/`, `~/.agents/skills/` and a project's `.agents/skills/`, and Codex's custom prompts in
`~/.codex/prompts/`; the projects are the folders conversations were handed to an agent in
(`core/conversation/agent_folders.py`). Both agents write a skill as a folder with a SKILL.md (a `name:` and
`description:` header, then the instructions) and files beside it, as the assistant does; a Codex prompt is one
Markdown file. `formats.py` reads them as the assistant's (`found.py`), `listing.py` says which were imported and
which changed since, and `importing.py` copies the ones the user picks, never linking, recording the source and
a digest of it in the copy (`records.py`), so a source that changed is offered as an update instead of synced.
AGENTS.md and CLAUDE.md files are listed as suggestions only: they are a coding agent's instructions for a
project, not skills.
"""
