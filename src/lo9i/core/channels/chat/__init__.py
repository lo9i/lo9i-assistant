"""Chats in the channels installed as plugins (Telegram, Slack), as the daemon runs them: a run shown as
chat messages (turn.py), approval and question buttons and what pressing them does (approvals.py,
questions.py, conversations.py), and which conversation each message belongs to (threads.py). The
channel's process only carries out the operations a chat needs (port.py): send, edit, typing, voice
(docs/channel-plugins.md)."""
