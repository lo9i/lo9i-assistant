---
name: writing-skills
description: Writing a skill: its name, description, steps and files. For save_skill.
---

A skill is reusable step-by-step instructions for a task you'll do again (a daily news digest, a monthly report), read with use_skill. The user approves every save, seeing the whole skill.

## Fields

- `name`: a short slug of lowercase letters, digits and hyphens, like news-digest. Saving under a name that exists replaces that skill; built-in skills can't be replaced.
- `description`: one line saying what it does and when to use it. It's all you'll see of the skill in later conversations, so make it name the requests it's for.
- `instructions`: the steps, written for yourself with nothing of this conversation: the tools to call, the sources and accounts to use, the exact format of the result, and what to do when something fails or is missing.
- `files`: scripts or reference files kept in the skill's folder, as {relative path: content}, like {"scripts/report.py": "..."} (usually under `scripts/`, `references/` or `assets/`). Refer to them by that path in the instructions: use_skill shows the skill's folder, and paths are relative to it. A save whose instructions name a file the skill doesn't have is refused. Giving `files` replaces all of the skill's files; leaving it out keeps them.

## Good skills

- One task per skill. How the user wants that task done ("show the due date first") goes here, not in the profile.
- Steps the model can follow without guessing: exact commands, URLs and names.
- Never put tokens or passwords in a skill. A task that needs a secret, an outside service or a connection that stays open needs a plugin instead (offer_plugin).
- A saved skill shows in the skill list from the next epoch; use_skill works at once. A scheduled job can run it ("Run the skill news-digest").
