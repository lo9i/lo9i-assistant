"""The parts of the security audit that read only this computer, so `lo9i security audit` runs them while the daemon
is down too: where the daemon listens, who can connect to its socket, who can read its data, and when bash asks
first. Each reads settings and a few files' modes, quick enough to run in a thread."""

import ipaddress
from pathlib import Path

import psutil

from lo9i.core.config import settings
from lo9i.core.i18n import said
from lo9i.core.security_audit import access
from lo9i.core.setup_check.model import SetupCheck

# The pages' port is the API's plus this (daemon/pages.py's PORT_OFFSET, which core can't import).
PAGES_OFFSET = 1
_WILDCARDS = ("0.0.0.0", "::", "")
_RESTART = said("Stop whatever made it, then restart the daemon: lo9i daemon restart.")


def local_ports(port: int) -> SetupCheck:
    """The plain-HTTP listeners, which daemon/server.py binds to 127.0.0.1 only."""
    detail = said(
        "Only this computer: 127.0.0.1:{port} (the API) and :{pages} (plugins' pages), each needing a paired device.",
        port=port,
        pages=port + PAGES_OFFSET,
    )
    return SetupCheck("network:local", said("Local ports"), "ok", detail)


def https(port: int, bind: str, hosts: list[str], addresses: list[str]) -> SetupCheck:
    """The HTTPS listener for other computers (settings `https_*`); `addresses`, this computer's own, which a
    wildcard bind answers on."""
    title = said("HTTPS for other computers")
    if port <= 0:
        return SetupCheck("network:https", title, "ok", said("Off: no port is open to other computers."))
    ports = f"{port}, {port + PAGES_OFFSET}"
    names = ", ".join(hosts) or said("no name set")
    if bind in _WILDCARDS:
        detail = said(
            "Ports {ports} on every interface ({addresses}), for {names}.",
            ports=ports,
            addresses=", ".join(addresses) or bind,
            names=names,
        )
        fix = said("Set HTTPS_BIND in .env to the one address browsers use (a Tailscale address, say).")
        return SetupCheck("network:https", title, "warn", detail, fix)
    detail = said("Ports {ports} on {bind} only, for {names}.", ports=ports, bind=bind, names=names)
    return SetupCheck("network:https", title, "ok", detail)


def addresses() -> list[str]:
    """This computer's addresses other than loopback and link-local, which a wildcard bind is reached on."""
    found = [a.address.split("%")[0] for nic in psutil.net_if_addrs().values() for a in nic]
    return sorted({a for a in found if _reachable(a)})


def _reachable(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (ip.is_loopback or ip.is_link_local)


def socket(path: Path) -> SetupCheck:
    """The Unix socket is trusted without a device (daemon/auth.py), so whoever can connect to it is the owner."""
    title = said("Daemon socket")
    if not path.exists():
        return SetupCheck("socket", title, "ok", said("Not there: the daemon isn't running."))
    if not access.owned_by_me(path):
        return SetupCheck("socket", title, "fail", said("{path} belongs to another user.", path=str(path)), _RESTART)
    others = access.writers(path)
    if others:
        detail = said("{who} can connect to {path} and act as you.", who=_who(others), path=str(path))
        return SetupCheck("socket", title, "fail", detail, f"chmod 700 {path.parent}")
    return SetupCheck("socket", title, "ok", said("Only you can connect to {path}.", path=str(path)))


def data_folder(folder: Path) -> SetupCheck | None:
    """lo9i's data folder: its files are judged on their own, but a folder others can list shows what's in it."""
    if not folder.is_dir():
        return None
    title = said("Data folder")
    others = access.readers(folder)
    if others:
        detail = said(
            "{who} can list {path} (mode {mode}).", who=_who(others), path=str(folder), mode=access.mode(folder)
        )
        return SetupCheck("permissions:home", title, "warn", detail, f"chmod 700 {folder}")
    return SetupCheck("permissions:home", title, "ok", said("Only you can open {path}.", path=str(folder)))


def private_file(check_id: str, title: str, paths: list[Path]) -> SetupCheck | None:
    """Files only their owner should read: anyone else reading one fails, its group warns. None when none is there."""
    there = [p for p in paths if p.exists()]
    if not there:
        return None
    foreign = [p for p in there if not access.owned_by_me(p)]
    if foreign:
        detail = said("{path} belongs to another user.", path=str(foreign[0]))
        return SetupCheck(check_id, title, "fail", detail, said("chown it back to you, or delete it."))
    readable = {p: access.readers(p) for p in there if access.readers(p)}
    if readable:
        return _readable(check_id, title, readable)
    return SetupCheck(check_id, title, "ok", said("Only you can read {path}.", path=str(there[0])))


def _readable(check_id: str, title: str, readable: dict[Path, list[access.Others]]) -> SetupCheck:
    path = next(iter(readable))
    widest = max(readable.values(), key=len)
    detail = said("{who} can read {path} (mode {mode}).", who=_who(widest), path=str(path), mode=access.mode(path))
    fix = "chmod 600 " + " ".join(str(p) for p in readable)
    return SetupCheck(check_id, title, "fail" if "everyone" in widest else "warn", detail, fix)


def bash_guard(approval: str, toolsets: list[str]) -> SetupCheck:
    """When the agent's bash asks first (settings `bash_approval`, core/tools/bash_guard.py)."""
    title = said("Bash approval")
    if "terminal" not in toolsets:
        return SetupCheck("bash", title, "ok", said("Off: the agent has no bash."))
    match approval:
        case "always":
            return SetupCheck("bash", title, "ok", said("Every command asks you first."))
        case "dangerous":
            detail = said("Commands the guard finds dangerous (deleting, sudo, piping to a shell...) ask you first.")
            return SetupCheck("bash", title, "ok", detail)
        case _:
            detail = said("The agent runs every command without asking, as you.")
            fix = said("Set BASH_APPROVAL=dangerous (or always) in .env, then restart the daemon.")
            return SetupCheck("bash", title, "warn", detail, fix)


def _who(others: list[access.Others]) -> str:
    return said("Every user") if "everyone" in others else said("Your group")


def checks() -> list[SetupCheck]:
    """Every local part, from the settings: what the command runs while the daemon is down, and the daemon runs too."""
    home = Path(settings.database_path).expanduser().parent
    database = Path(settings.database_path).expanduser()
    found = [
        local_ports(settings.daemon_port),
        https(settings.https_port, settings.https_bind, settings.https_hosts, addresses()),
        socket(Path(settings.daemon_socket).expanduser()),
        data_folder(home),
        private_file("permissions:database", said("Database"), [database, *_sidecars(database)]),
        private_file("permissions:secrets", said("Secret key"), [Path(settings.secrets_key_path).expanduser()]),
        private_file("permissions:env", ".env", _env_files()),
        private_file("permissions:https_key", said("HTTPS key"), _https_key()),
        private_file("permissions:setup_code", said("Setup code file"), [Path(settings.setup_code_path).expanduser()]),
        bash_guard(settings.bash_approval, settings.toolsets),
    ]
    return [c for c in found if c is not None]


def _sidecars(database: Path) -> list[Path]:
    """SQLite's write-ahead log and shared memory, which hold recent writes as the database does."""
    return [database.with_name(database.name + suffix) for suffix in ("-wal", "-shm")]


def _env_files() -> list[Path]:
    """The .env files settings read (core/config.py): they hold the model's key."""
    files = settings.model_config.get("env_file") or ()
    return [Path(f).resolve() for f in ((files,) if isinstance(files, str | Path) else files)]


def _https_key() -> list[Path]:
    return [Path(settings.https_key).expanduser()] if settings.https_port > 0 and settings.https_key else []
