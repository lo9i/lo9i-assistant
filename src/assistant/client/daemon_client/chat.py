from assistant.client.daemon_client.transport import Transport


class ChatBase:
    """The transport shared by the conversation mixins."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
