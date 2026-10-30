"""The folder a conversation is handed to (core/conversation/handoffs.py), as the apps' folder panel shows it while the
agent works there: what's inside, one folder at a time (contents.py), with what git says was deleted where it was
(tree.py), a file's text (preview.py), what git says changed (changes.py) and a changed file's diff (diff.py). Only
what's inside the folder is read (paths.py), and only what the tree shows: never .git, node_modules, .venv or what
git ignores, so a .env the agent's project keeps out of git isn't shown either. It works the same for every agent
plugin: it reads the folder, not the agent. A conversation not handed to one shows the user's home folder the same
way, without its changes. In either, the user can delete a file the tree shows, which goes to the system's trash
(deleting.py, trash.py).
"""
