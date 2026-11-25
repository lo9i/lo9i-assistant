"""Model API errors that mean the request was too large: more bytes than the API takes (HTTP 413, GitHub Copilot's
"Request Entity Too Large") or more tokens than the model's context window. LangChain turns some of the latter into
`ContextOverflowError`; the rest each provider says its own way, in the error's text."""

from langchain_core.exceptions import ContextOverflowError

_TOO_LARGE_STATUS = 413
_TOO_LARGE_TEXTS = (
    "request entity too large",
    "request_too_large",
    "context_length_exceeded",
    "model_max_prompt_tokens_exceeded",
    "maximum context length",
    "exceeds the context window",
    "prompt is too long",
)


def too_large(error: BaseException) -> bool:
    if isinstance(error, ContextOverflowError) or getattr(error, "status_code", None) == _TOO_LARGE_STATUS:
        return True
    text = str(error).lower()
    return any(marker in text for marker in _TOO_LARGE_TEXTS)


# The provider's side: out of requests or quota (429, Copilot's and others' 402), overloaded (Anthropic's 529), or
# down (5xx). A request the provider refuses for what it says (400, 401, 404, 413) isn't one: a backup would refuse it
# too, or the user has to fix it.
_PROVIDER_STATUSES = frozenset({402, 408, 429})
# Errors without a status: the connection failed or timed out (the SDKs' and httpx's classes, by name, so no
# provider's package has to be installed to tell them).
_UNREACHABLE = frozenset(
    {"APIConnectionError", "APITimeoutError", "TransportError", "TimeoutException", "ConnectError", "TimeoutError"}
)


def provider_failed(error: BaseException) -> bool:
    """The call failed on the provider's side (core/llm/backups.py tries a backup model then), not for what was
    asked."""
    if too_large(error):
        return False
    status = _status(error)
    if status is not None:
        return status in _PROVIDER_STATUSES or status >= 500
    return any(cls.__name__ in _UNREACHABLE for cls in type(error).__mro__)


def _status(error: BaseException) -> int | None:
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    return status if isinstance(status, int) else None
