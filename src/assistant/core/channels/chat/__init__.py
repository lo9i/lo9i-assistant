"""Chats in the channels installed as plugins (Telegram, Slack), as the daemon runs them: a run shown as
chat messages (turn.py), approval, question and side-conversation buttons and what pressing them does
(approvals.py, questions.py, side.py, conversations.py). The channel's process only carries out the
operations a chat needs (port.py): send, edit, typing, voice (docs/channel-plugins.md)."""
