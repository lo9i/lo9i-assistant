---
name: writing-briefs
description: When to delegate or move work out of the inbox, and how to write a subagent's brief. For delegate and move_to_conversation.
---

A subagent starts with nothing of this conversation: the brief is all it gets.

## When to delegate

- Use delegate for work that would fill this conversation with output you only need a summary of: research across many pages, digging through files or logs, comparing many results.
- A subagent can run commands, search the web, read email and memory, use skills and the read-only tools of the plugins this conversation loaded and of those you name in delegate's `plugins`. It can't message the user, send, schedule or save anything: do those yourself with what it answers.
- Several delegate calls in one reply run in parallel: split independent parts (one source each, one folder each) into separate calls.
- Small tasks (one command, one page) are quicker done yourself.

## Waiting or in the background

- By default delegate waits for the answer, and the subagent stops after a set number of steps: for a quick job whose answer you need before you reply.
- With `background: true` it's sent off and the call returns at once: for long work (a deep research, a big search through files) that the user shouldn't wait for. It has no step limit, the user keeps talking to you meanwhile and sees its progress in the app, and an approval it needs pauses only it. Tell the user in a line that it's working on it, then go on with what they say.
- Its answer comes back to this conversation when it ends, and you're asked to follow it up then: don't wait for it, ask for it, or do its work yourself meanwhile.
- In a scheduled job a background subagent waits like any other: the job ends with its reply.

## When to move out of the inbox

The inbox only answers quick questions. Use move_to_conversation as soon as what the user asks there will take more than a couple of turns: a project, a long research, debugging something, a plan. Nobody is asked and you write nothing: the user's message goes to a new conversation as they wrote it, with the quick exchange before it, it's answered there, and the user is taken there. Say so in one short line and don't start the work in the inbox. It does nothing outside the inbox or in a scheduled run.

## Writing a subagent's brief

Say everything it needs, as if to someone who wasn't there:

- The goal, and what done looks like.
- The names, ids, paths, URLs, accounts and versions involved, exactly as they were given.
- What's already known or was tried, and what was decided so far (and what was ruled out).
- What the user just asked, in their words when they matter.
- What to return: the format, how long, what to leave out ("the three cheapest, each with its price and link").
