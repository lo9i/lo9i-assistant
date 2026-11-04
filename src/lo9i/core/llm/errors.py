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
