"""The bash sandbox: when the user turns it on (Settings → General, off until then), the bash tool's commands run in a
container of Docker or Podman, whichever this computer has, with only the workspace mounted, so they can't read lo9i's
data folder (its database and the secrets' key) or the user's other files (BACKLOG R1). runtime.py finds the container
runtime and asks whether it answers; setting.py keeps whether it's on; container.py runs a command in it and says in
plain words why one didn't run there."""
