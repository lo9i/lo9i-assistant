"""Home: the page the web app opens on, built by the assistant from the plugins' tools.

Each section is a text the user edits (sections.py), like "today's events". To build it, the worker model reads
the read-only tools of the plugins the section names (builder.py) and answers in one structured format, the
items with their date and time (model.py). The last result of each section is kept in the Store (results.py),
so Home shows it at once; a refresh runs in the background and each section's result is saved as it's ready
(refresh.py). A section whose plugins aren't there, or whose building fails, says so without stopping the others.
"""
