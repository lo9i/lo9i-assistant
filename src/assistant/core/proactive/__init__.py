"""The assistant's own initiative, on for every user and changed from the apps (the web app's Briefing page and
Settings → General, the terminal app's /briefing):

- the morning briefing (briefing.py): today's calendar, what's due, important mail, the open loops that matter now and
  the reviews' suggestions, sent to the user's chat channels and kept in the notifications feed;
- open loops (loops.py): what's still to do, from conversations' archived parts, the briefing and the reviews, closed
  when a later conversation or review shows it done, and by the user;
- reminders (reminders.py) of the urgent ones at their time;
- the nightly and weekly reviews (review.py), which suggest and remember habits, and never act for the user;
- the kinds of suggestion the user muted (`ProactiveSettings.muted`), never made again.

Everything runs on the worker model, gathering only from the sources the user has (sources.py)."""
