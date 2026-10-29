"""The files waiting to go with the next message, shown as tags inside the message box, before
the text. Backspace in an empty message box removes the last one."""

from textual.containers import Horizontal
from textual.widgets import Static

from assistant.core.attachments import Attachment
from assistant_terminal.i18n import decimal


class AttachmentBar(Horizontal):
    """Hidden while nothing is attached."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tags: list[_Tag] = []

    @property
    def pending(self) -> list[Attachment]:
        return [tag.attachment for tag in self._tags]

    async def add(self, attachment: Attachment) -> None:
        tag = _Tag(attachment)
        self._tags.append(tag)
        await self.mount(tag)
        self._update()

    async def remove_last(self) -> None:
        if self._tags:
            await self._tags.pop().remove()
            self._update()

    async def clear(self) -> None:
        self._tags = []
        await self.remove_children()
        self._update()

    def _update(self) -> None:
        self.set_class(bool(self._tags), "visible")


class _Tag(Static):
    def __init__(self, attachment: Attachment) -> None:
        super().__init__(f"[{attachment.name} {_size(len(attachment.data))}]", markup=False, classes="tag")
        self.attachment = attachment


def _size(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.0f} KB"
    return f"{decimal(count / (1024 * 1024))} MB"
