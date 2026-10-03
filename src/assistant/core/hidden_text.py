"""Text from outside (MCP servers, email) cleaned of characters the model reads but people don't see."""

import re

# Unicode tag characters render as nothing but the model reads them, so a sender can hide
# instructions in them. They are kept only inside emoji tag sequences (subdivision flags).
_TAGS = re.compile("(\U0001f3f4[\U000e0020-\U000e007e]+\U000e007f)|[\U000e0000-\U000e007f]")


def strip_hidden(text: str) -> str:
    return _TAGS.sub(lambda match: match.group(1) or "", text)
