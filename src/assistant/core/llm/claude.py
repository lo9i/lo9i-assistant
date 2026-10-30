"""Claude through Anthropic's API, on connections that notice when they died (core/llm/connections.py)."""

from functools import cached_property

import anthropic
from langchain_anthropic import ChatAnthropic

from assistant.core.llm import connections


class KeptAliveChatAnthropic(ChatAnthropic):
    """langchain-anthropic (1.7) makes its SDK client itself, on the SDK's default connections, with no way to pass
    one in. Its async client, the one every call of the assistant's goes through, is made here the same way on
    connections.py's sockets, until the library takes one (BACKLOG.md, A2)."""

    @cached_property
    def _async_client(self) -> anthropic.AsyncClient:
        return anthropic.AsyncClient(**self._client_params, http_client=connections.httpx2_client())
