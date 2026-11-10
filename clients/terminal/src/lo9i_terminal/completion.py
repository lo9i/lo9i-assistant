"""`lo9i completion <shell>`: the completion script for bash, zsh or fish, written from the commands cli.py parses, so
the two never differ. install.sh installs the one for the user's shell."""

from lo9i_terminal.cli import COMMANDS, DAEMON_ACTIONS, SHELLS

_DOCTOR_OPTIONS = ("--json",)
_IMPORT_OPTIONS = ("--force",)
_TOP_OPTIONS = ("--help", "--version")


def script(shell: str) -> str:
    return {"bash": _bash, "zsh": _zsh, "fish": _fish}[shell]()


def _bash() -> str:
    top = " ".join([*COMMANDS, *_TOP_OPTIONS])
    return f"""# lo9i completion for bash: lo9i completion bash > ~/.local/share/bash-completion/completions/lo9i
_lo9i() {{
  local cur="${{COMP_WORDS[COMP_CWORD]}}"
  case "$COMP_CWORD:${{COMP_WORDS[1]}}" in
    1:*) COMPREPLY=($(compgen -W "{top}" -- "$cur")) ;;
    2:daemon) COMPREPLY=($(compgen -W "{" ".join(DAEMON_ACTIONS)}" -- "$cur")) ;;
    2:doctor) COMPREPLY=($(compgen -W "{" ".join(_DOCTOR_OPTIONS)}" -- "$cur")) ;;
    2:export) COMPREPLY=($(compgen -f -- "$cur")) ;;
    *:import) COMPREPLY=($(compgen -W "{" ".join(_IMPORT_OPTIONS)}" -f -- "$cur")) ;;
    2:completion) COMPREPLY=($(compgen -W "{" ".join(SHELLS)}" -- "$cur")) ;;
  esac
}}
complete -F _lo9i lo9i
"""


def _zsh() -> str:
    described = "\n".join(f"    {_quoted(f'{name}:{text}')}" for name, text in COMMANDS.items())
    return f"""#compdef lo9i
# lo9i completion for zsh: lo9i completion zsh > a folder on $fpath, as _lo9i
_lo9i() {{
  local -a commands
  commands=(
{described}
  )
  if (( CURRENT == 2 )); then
    _describe command commands
    compadd -- {" ".join(_TOP_OPTIONS)}
    return
  fi
  case $words[2] in
    daemon) compadd -- {" ".join(DAEMON_ACTIONS)} ;;
    doctor) compadd -- {" ".join(_DOCTOR_OPTIONS)} ;;
    export) _files ;;
    import) compadd -- {" ".join(_IMPORT_OPTIONS)}; _files ;;
    completion) compadd -- {" ".join(SHELLS)} ;;
  esac
}}
if [[ "${{funcstack[1]}}" == "_lo9i" ]]; then
  _lo9i "$@"
else
  compdef _lo9i lo9i
fi
"""


def _fish() -> str:
    lines = [
        "# lo9i completion for fish: lo9i completion fish > ~/.config/fish/completions/lo9i.fish",
        "complete -c lo9i -f",
        "complete -c lo9i -n __fish_use_subcommand -l version -d 'Show the version'",
    ]
    lines += [
        f"complete -c lo9i -n __fish_use_subcommand -a {name} -d {_fish_quoted(text)}"
        for name, text in COMMANDS.items()
    ]
    lines += [
        f"complete -c lo9i -n '__fish_seen_subcommand_from daemon' -a '{' '.join(DAEMON_ACTIONS)}'",
        "complete -c lo9i -n '__fish_seen_subcommand_from doctor' -l json -d 'Print the report as JSON'",
        "complete -c lo9i -n '__fish_seen_subcommand_from export import' -F",
        "complete -c lo9i -n '__fish_seen_subcommand_from import' -l force -d 'Replace the data lo9i has here'",
        f"complete -c lo9i -n '__fish_seen_subcommand_from completion' -a '{' '.join(SHELLS)}'",
    ]
    return "\n".join(lines) + "\n"


def _quoted(text: str) -> str:
    """In single quotes for bash or zsh, a quote in it closed, escaped and opened again."""
    return "'" + text.replace("'", "'\\''") + "'"


def _fish_quoted(text: str) -> str:
    """In single quotes for fish, which escapes a quote and a backslash inside them."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"
