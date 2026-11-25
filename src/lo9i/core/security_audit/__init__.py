"""The security audit (`lo9i security audit`): how exposed lo9i is on this computer and its network, each part ok, a
warning or failing, with a one-line fix, in the setup check's format (core/setup_check/model.py).

Some parts read only this computer (local.py: the ports the daemon listens on, its socket, the permissions of its
data folder, database, secret key and .env, the bash approval guard), so the command runs them while the daemon is
down too; the rest read the daemon's state (service.py: paired devices, the setup code, the plugins and MCP servers
that run commands here), which the daemon checks (core/agent/security_audit.py, `GET /security-audit`)."""

from lo9i.core.security_audit import local, service

__all__ = ["local", "service"]
