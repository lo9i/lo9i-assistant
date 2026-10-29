"""The GitHub Copilot plan's allowance, watched without the model: the point is to say the model may be out of
quota, so nothing here calls one. While the model provider is Copilot, the daemon reads what GitHub reports to
VS Code (quota.py) at start and every few hours (watch.py), keeps the last check (records.py), shows it on Home's
Copilot card (section.py, a section built by code: core/home/coded.py), and tells the user on WhatsApp once when
the allowance runs low and once when it runs out, each at most once per period (alerts.py)."""
