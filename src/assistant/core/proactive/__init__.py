"""The assistant's own initiative, on for every user and changed from the apps (the web app's Briefing page and
Settings → General, the terminal app's /briefing):

- the morning briefing (briefing.py): each plugin's list for the day (core/mcp/today.py), the unread mail that matters,
  the open loops that matter now and the reviews' suggestions, laid out by code, sent to the user's chat channels and
  kept in the notifications feed;
- open loops (loops.py): what's still to do, from conversations' archived parts, the briefing and the reviews, closed
  when a later conversation or review shows it done, and by the user;
- reminders (reminders.py) of the urgent ones at their time;
- the nightly and weekly reviews (review.py), which suggest and remember habits, and never act for the user;
- the kinds of suggestion the user muted (`ProactiveSettings.muted`), never made again.

The plugins' lists are read by code, never by a model; the worker model only picks the unread mail that matters and
writes the reviews."""
