from assistant_terminal import i18n
from assistant_terminal.approval_text import approval_title, approval_why, call_lines

_CALL = {
    "server": "billing",
    "tool": "create_invoice",
    "does": "Issue an invoice.",
    "arguments": [],
    "why": "asks_first",
}
_REQUEST = {"tool": "mcp__billing__create_invoice", "command": "{}", "reason": "asks", "call": _CALL}


def test_an_mcp_tools_call_reads_in_words() -> None:
    assert approval_title(_REQUEST) == "Approve create_invoice from billing?"
    assert approval_why(_REQUEST) == "billing asks before each use of this tool."
    assert call_lines(_CALL) == ["Issue an invoice.", "No arguments: it runs with its defaults."]
    given = {**_CALL, "arguments": [{"name": "customer", "about": "Its id or CUIT", "value": "acme"}]}
    assert call_lines(given) == ["Issue an invoice.", "• customer: acme (Its id or CUIT)"]


def test_it_reads_in_spanish_and_other_requests_keep_their_tool_and_reason() -> None:
    i18n.use("es")
    try:
        assert approval_title(_REQUEST) == "¿Aprobar create_invoice de billing?"
        assert approval_title({"tool": "bash", "reason": "recursive delete"}) == "¿Aprobar bash?"
        assert approval_why({"tool": "bash", "reason": "recursive delete"}) == "recursive delete"
    finally:
        i18n.use("en")
