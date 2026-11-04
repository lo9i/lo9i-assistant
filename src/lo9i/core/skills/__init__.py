"""Skills: reusable instructions saved as Markdown, `<skills_dir>/<name>/SKILL.md`.

The system prompt lists each skill's name and description; the full instructions are loaded only
when the agent uses a skill, which keeps the prompt small and stable. Built-in skills ship with the
app (`builtin/`), are listed with the user's, and can't be replaced or deleted.
"""
