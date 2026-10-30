"""Text written for people now and shown later in their language (core/i18n): an error's message. Apart from
core/i18n so that modules it reads, like core/language.py, can write theirs too."""


class Said(str):
    """Text written for people and shown later, an error's message: it reads as its English, so a log or the model
    gets that, and keeps its text and values so `Texts.shown` writes it in a language. A value may be one too."""

    text: str
    values: dict[str, object]

    def __new__(cls, text: str, /, **values: object) -> "Said":
        said = super().__new__(cls, text.format(**values) if values else text)
        said.text, said.values = text, values
        return said


def said(text: str, /, **values: object) -> Said:
    """`text`, in English with its {placeholders} filled from `values`, shown later in the language of whoever
    reads it. Marked for translation like `t`."""
    return Said(text, **values)


def message(error: BaseException) -> str:
    """What `error` says, a `said` text kept as one: raised with one, or with one in its `message`."""
    for found in (*error.args[:1], getattr(error, "message", None)):
        if isinstance(found, Said):
            return found
    return str(error)


def holds_said(value: object) -> bool:
    """Whether `value`, or a list, tuple or dict in it, has a `said` text: what needs showing in a language."""
    if isinstance(value, Said):
        return True
    if isinstance(value, list | tuple):
        return any(holds_said(item) for item in value)
    return isinstance(value, dict) and any(holds_said(item) for item in value.values())
