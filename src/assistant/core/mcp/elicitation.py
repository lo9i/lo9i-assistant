"""A server's form for the user (MCP elicitation) as the apps show it, and the user's answer as the server takes it.

A form request (`kind: "form"`, core/events.py) names the server that asks (`asked_by`), its `message`, and either
`fields`, each with a `key`, `title`, `description`, `type` (text, number, integer, boolean, choice or choices),
`required`, `default` and, for a choice, its `options` (`value` and `label`); or a `url` the server asks the user to
open, for what mustn't pass through lo9i (a payment, a sign-in). It's answered with
`{"action": "accept", "content": {...}}`, `{"action": "decline"}` or `{"action": "cancel"}`. What the server writes is
shown as text, its hidden characters taken out."""

from typing import Any

from mcp.types import ElicitRequestFormParams, ElicitRequestParams, ElicitResult

from assistant.core.events import FORM
from assistant.core.hidden_text import strip_hidden

_TEXT_FORMATS = ("email", "uri", "date", "date-time")


def request(server: str, params: ElicitRequestParams) -> dict[str, Any] | None:
    """The form to show, or None for one that can't be: a link that isn't a web address."""
    shown = {"kind": FORM, "asked_by": server, "message": strip_hidden(params.message)}
    if isinstance(params, ElicitRequestFormParams):
        properties = params.requested_schema.get("properties") or {}
        required = set(params.requested_schema.get("required") or [])
        return shown | {"fields": [_field(key, schema, key in required) for key, schema in properties.items()]}
    if not params.url.startswith(("https://", "http://")):
        return None
    return shown | {"url": params.url}


def result(form: dict[str, Any], answer: dict[str, Any]) -> ElicitResult:
    """The user's answer for the server: content only when accepted, each field as its type, and a required one
    missing cancels it. A chat channel answers a link, or a form with nothing to fill in, with its approval buttons
    (core/channels/chat/forms.py): approved accepts it, rejected declines it."""
    action = answer.get("action") or _approved(answer)
    if action not in ("accept", "decline"):
        return ElicitResult(action="cancel")
    if action == "decline" or "url" in form:
        return ElicitResult(action=action)
    content = _content(form["fields"], answer.get("content") or {})
    return ElicitResult(action="accept", content=content) if content is not None else ElicitResult(action="cancel")


def _approved(answer: dict[str, Any]) -> str | None:
    if "approved" not in answer:
        return None
    return "accept" if answer["approved"] else "decline"


def declined() -> ElicitResult:
    return ElicitResult(action="decline")


def _field(key: str, schema: dict[str, Any], required: bool) -> dict[str, Any]:
    kind, options = _kind(schema)
    field: dict[str, Any] = {
        "key": key,
        "title": strip_hidden(str(schema.get("title") or key)),
        "description": strip_hidden(str(schema.get("description") or "")),
        "type": kind,
        "required": required,
    }
    if "default" in schema:
        field["default"] = schema["default"]
    if options:
        field["options"] = options
    if kind == "text" and schema.get("format") in _TEXT_FORMATS:
        field["format"] = schema["format"]
    return field


def _kind(schema: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Its type for the apps, and a choice's options, from the primitive types a form may have."""
    if schema.get("type") == "array":
        return "choices", _options(schema.get("items") or {})
    if options := _options(schema):
        return "choice", options
    kind = schema.get("type")
    return (kind if kind in ("number", "integer", "boolean") else "text"), []


def _options(schema: dict[str, Any]) -> list[dict[str, str]]:
    """Choices given as `enum` (with `enumNames` for their labels) or as `oneOf`/`anyOf` items with a `const` and a
    `title`."""
    if values := schema.get("enum"):
        labels = schema.get("enumNames") or values
        return [{"value": str(v), "label": strip_hidden(str(label))} for v, label in zip(values, labels, strict=False)]
    items = schema.get("oneOf") or schema.get("anyOf") or []
    return [
        {"value": str(i["const"]), "label": strip_hidden(str(i.get("title") or i["const"]))}
        for i in items
        if "const" in i
    ]


def _content(fields: list[dict[str, Any]], given: dict[str, Any]) -> dict[str, Any] | None:
    content: dict[str, Any] = {}
    for field in fields:
        value = _value(field, given.get(field["key"]))
        if value is None:
            if field["required"]:
                return None
            continue
        content[field["key"]] = value
    return content


def _value(field: dict[str, Any], given: Any) -> Any:
    """The value as the field's type, or None for one not given or not of it."""
    if given is None or given == "":
        return None
    try:
        match field["type"]:
            case "number":
                return float(given)
            case "integer":
                return int(given)
            case "boolean":
                return given if isinstance(given, bool) else str(given).lower() in ("true", "yes", "1")
            case "choice":
                return str(given) if str(given) in {o["value"] for o in field["options"]} else None
            case "choices":
                values = {o["value"] for o in field["options"]}
                picked = [str(v) for v in given] if isinstance(given, list) else []
                return [v for v in picked if v in values]
            case _:
                return str(given)
    except (TypeError, ValueError):
        return None
