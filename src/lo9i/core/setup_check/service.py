"""The parts of the setup check that read the daemon's own state: the model and its key, each plugin's MCP server,
each email account and each chat channel. Pure: the daemon gathers what they read (core/agent/setup_check.py)."""

from lo9i.core.health import Health
from lo9i.core.i18n import said
from lo9i.core.llm.key_check import KeyVerdict
from lo9i.core.setup_check.model import SetupCheck

_MODEL_FIX = said("Set it in Settings → Model (/model in the terminal app).")
_KEY_FIX = said("Enter a working key in Settings → Model (/model in the terminal app).")
_PLUGIN_FIX = said("See its error in Settings → MCP servers (/mcp), and Settings → Logs.")
_SIGN_IN_FIX = said("Sign in again in Settings → MCP servers (/mcp).")
_EMAIL_FIX = said("Connect it again in its plugin's details in Settings → Plugins (/plugins).")
_CHANNEL_FIX = said("See Settings → Logs (/logs) for its process; its settings are in Settings → Plugins (/plugins).")


def model(provider: str, model_id: str, missing: str, verdict: KeyVerdict | None) -> SetupCheck:
    """`provider`'s name ("" for one lo9i doesn't know), the main model, the label of a required field left empty,
    and what checking its key said (None when it wasn't checked, something being missing)."""
    title = said("Model")
    if not provider:
        return SetupCheck("model", title, "fail", said("No known provider is set."), _MODEL_FIX)
    if missing:
        return SetupCheck("model", title, "fail", said("{label} isn't set.", label=missing), _MODEL_FIX)
    if not model_id:
        return SetupCheck("model", title, "fail", said("No model is set."), _MODEL_FIX)
    return _key(title, provider, model_id, verdict or KeyVerdict("unchecked"))


def _key(title: str, provider: str, model_id: str, verdict: KeyVerdict) -> SetupCheck:
    match verdict.state:
        case "works":
            return SetupCheck(
                "model", title, "ok", said("{provider}, {model}: the key works.", provider=provider, model=model_id)
            )
        case "refused":
            detail = said("{provider} refused the key: {reason}", provider=provider, reason=verdict.reason)
            return SetupCheck("model", title, "fail", detail, _KEY_FIX)
        case "unreachable":
            detail = said("Couldn't reach {provider}: {reason}", provider=provider, reason=verdict.reason)
            return SetupCheck(
                "model", title, "warn", detail, said("Check the network, or the server URL in Settings → Model.")
            )
        case "unchecked":
            detail = said(
                "{provider}, {model}. Its key is checked when a model answers.", provider=provider, model=model_id
            )
            return SetupCheck("model", title, "ok", detail)


def plugin(name: str, status: str, error: str, tools: int, health: Health) -> SetupCheck:
    """An enabled plugin's MCP server: its connection's status (core/mcp/hub.py's `state`) and its failures in a row
    (core/health.py)."""
    check_id, title = f"plugin:{name}", said("Plugin {name}", name=name)
    if health.signed_out or status == "needs_sign_in":
        detail = (
            said("Its sign-in stopped working: {error}", error=health.error)
            if health.signed_out
            else said("Needs signing in.")
        )
        return SetupCheck(check_id, title, "fail", detail, _SIGN_IN_FIX)
    if status == "failed":
        return SetupCheck(check_id, title, "fail", said("Doesn't start: {error}", error=error), _PLUGIN_FIX)
    if health.failures:
        detail = said("Failed {count} times in a row: {error}", count=health.failures, error=health.error)
        return SetupCheck(check_id, title, "fail" if health.failing else "warn", detail, _PLUGIN_FIX)
    return _running(check_id, title, status, tools)


def _running(check_id: str, title: str, status: str, tools: int) -> SetupCheck:
    match status:
        case "connected":
            return SetupCheck(check_id, title, "ok", said("Connected, {count} tools.", count=tools))
        case "idle":
            return SetupCheck(check_id, title, "ok", said("Starts when one of its tools is called."))
        case "connecting":
            return SetupCheck(check_id, title, "warn", said("Starting."), said("Check again in a moment."))
        case _:
            return SetupCheck(
                check_id,
                title,
                "warn",
                said("Not started."),
                said("Turn it off and on in Settings → MCP servers (/mcp)."),
            )


def email(account_id: str, name: str, status: str, problem: str) -> SetupCheck:
    """An email account as it was last used: its status says when it needs connecting again."""
    check_id, title = f"email:{account_id}", said("Email {name}", name=name)
    if status == "ok":
        return SetupCheck(check_id, title, "ok", said("Connected."))
    return SetupCheck(check_id, title, "fail", problem or said("Needs connecting again."), _EMAIL_FIX)


def channel(name: str, connected: bool, problem: str) -> SetupCheck:
    """An enabled chat channel: its process connected to the daemon, or why it can't run here."""
    check_id, title = f"channel:{name}", said("Channel {name}", name=name)
    if problem:
        return SetupCheck(check_id, title, "fail", problem, said("Update it in Settings → Plugins (/plugins)."))
    if connected:
        return SetupCheck(check_id, title, "ok", said("Connected."))
    return SetupCheck(check_id, title, "fail", said("Its process isn't connected."), _CHANNEL_FIX)
