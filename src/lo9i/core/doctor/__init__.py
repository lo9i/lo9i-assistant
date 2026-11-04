"""The doctor: checks the daemon's health once a day, so problems show without anyone reading the logs. A check
reads a day's records in the daemon's log and the conversations' checkpoints, groups what went wrong by cause
(log_causes.py, conversation_causes.py, causes.py), measures the context a new conversation starts with
(context.py), and compares both with the day before (changes.py). Causes marked as known noise are left out. The
report is kept (records.py), told in the notifications feed, and its new or growing causes and a starting context
past ALERT_SHARE of the window are alerts until dismissed. The daemon checks each day once it ended (schedule.py);
the apps check today so far (doctor.py). Nothing here calls a model."""
