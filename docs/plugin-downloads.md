# Plugin downloads

A plugin that downloads files outside lo9i's data home (videos, audio) can say where they go, so Settings → System's
Disk use and `lo9i clean` count them and clean them when the user asks. lo9i reads it in `core/mcp/downloads.py`.

It's `downloads:` in the plugin's `server.yaml`:

```yaml
downloads:
  field: YOUTUBE_DIR       # the field whose value is the folder
  default: ~/Downloads     # the folder while that field is empty; {data} is the plugin's data folder
  files: ['.* \[[\w-]{11}\]\.(mp4|mp3)']
```

- `field`: one of the plugin's fields; its value, as the user gave it, is the folder. Leave it out to always use
  `default`.
- `default`: the folder while the field is empty. `~` is the user's home folder.
- `files`: regular expressions (Python's), at least one; a file at the top of the folder whose whole name matches one is
  the plugin's. Only those are counted or cleaned, never the rest of the folder, which is the user's. Match only
  finished downloads: a file still being written should have a name the patterns leave out (yt-dlp's `.part`).

lo9i reads the section from the installed plugin's folder each time, so a plugin installed before it declared one counts
once it's updated. A daemon from before `downloads:` ignores the section and only doesn't count them, so it needs no new
`format:`. A section lo9i can't read is logged and the plugin's downloads aren't counted.

The downloads are cleaned only when the user names them (Clean on Downloads in Disk use, `lo9i clean downloads`), never
by cleaning everything.
