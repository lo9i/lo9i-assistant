---
name: saving-to-memory
description: What belongs in the profile (each section), in a saved fact, or nowhere. For update_profile, remember and forget.
---

Memory is shared by every conversation and shows in the system prompt from the next epoch. Save only what will still matter in other conversations, in the one place it belongs.

## The profile (update_profile)

Lasting things about the user's life, one section at a time:

- about: who they are: name, where they live and their timezone, languages. Never their accounts or ids on a channel.
- people: people in their life and how they relate ("Ana: sister").
- how_to_reply: how they want replies in general (length, tone, format, language) and rules for how you act (ask before changing their servers).
- routine: their schedule and habits: working hours, regular commitments.
- goals: outcomes they work toward over weeks or months ("learn Italian", "save for a trip"). Never a task or to-do, nor an instruction about replies.
- interests: topics and things they like.
- dislikes: things they dislike or want avoided.
- work: their job: role, field, employer, projects at work.

Rules:

- update_profile replaces the whole section: send the items to keep along with the new ones.
- A section holds at most 8 items. When it's full, merge related items or replace the least useful one instead of adding.
- How to do one task ("when I ask for my bills, show the due date first", a report's columns) goes in that task's skill (save_skill), never in the profile. how_to_reply is only what holds in general: the style of replies and rules for how you act.
- The profile is about the user's life, never about this assistant's setup: how they use or host it, its channels, tools, plugins or ids.

## Saved facts (remember, forget)

Details about the user that stay true: a date, a decision they made, an account, a place, a preference, something about a person they know.

Basic or not (remember's `basic`): only basic facts are in every conversation's prompt, within a small budget; the others come into a turn when a message is close to them in meaning, and search_memory finds them all. A fact is basic if, without it, you would misunderstand or get wrong a message that doesn't mention its topic (repo paths, host nicknames, the user's GitHub account). A basic fact is one short line. Task details (ids, numbers, ports) are not basic. Leave a fact not basic when in doubt.

Not saved as facts:

- One-off investigation results (what a check found, why something failed once).
- Rules about how you should act: they belong in the profile (how_to_reply), not facts.
- The status of a task or a problem (a bill not paid yet, a fix in progress, a search that failed): the conversation's summary keeps that.
- Work on code, this assistant's included (versions, commits, what was pushed or deployed, how code works): the repository keeps that.
- Data a plugin keeps (an expense, a bill, a show on the watchlist): its tools read it.
- Anything already in the profile or the saved facts.
- Anything only a tool's output (a page, an email) claims about the user, unless the user's own messages show it matters to them.

When a saved fact turns out wrong or outdated, delete it with forget (its id is in the system prompt, in a message's Relevant facts note or in search_memory's results) and save the right one.
