"""MCP tools as LangChain tools: approval on untrusted servers, a retry only where it's safe, and
results cleaned and cut to size. Images and audio in results are saved, not put in the checkpoint
(core/mcp/media.py)."""

import json
from typing import Any, Literal

from langchain_core.tools import BaseTool
from langgraph.runtime import get_runtime
from mcp.shared.exceptions import MCPError
from mcp.types import (
    AudioContent,
    CallToolResult,
    ContentBlock,
    EmbeddedResource,
    ImageContent,
    ResourceLink,
    TextContent,
    TextResourceContents,
)
from pydantic import ConfigDict, Field

from assistant.core.attachments import Block, is_reference
from assistant.core.background import current_origin
from assistant.core.config import settings
from assistant.core.context import Context
from assistant.core.hidden_text import strip_hidden
from assistant.core.mcp.connection import ConnectionLostError, McpConnection, NotConnectedError
from assistant.core.mcp.media import ToolMedia
from assistant.core.tools.approval import ask

_RECONNECT_SECONDS = 30

# The result's content (its text, and the transcripts of its audio), and references to its images.
Output = tuple[str | list[Block], list[Block]]


class McpTool(BaseTool):
    """One tool of a connected server, under the name the model sees (mcp__<server>__<tool>)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # References to images go in the tool message's artifact (core/attachments.py loads them).
    response_format: Literal["content", "content_and_artifact"] = "content_and_artifact"
    connection: McpConnection = Field(exclude=True)
    media: ToolMedia = Field(exclude=True)
    remote_name: str
    # Annotations are hints a server could lie about: on an untrusted server, a false read-only
    # claim can at most skip approval for that tool.
    read_only: bool = False
    trusted: bool = False

    def _run(self, *args: Any, **kwargs: Any) -> Output:
        raise NotImplementedError("MCP tools only run async.")

    async def _arun(self, **arguments: Any) -> Output:
        rejection = self._approve(arguments)
        if rejection:
            return rejection, []
        return await self._call(arguments)

    def _approve(self, arguments: dict[str, Any]) -> str | None:
        if self.trusted or self.read_only:
            return None
        server = self.connection.server.name
        request = {
            "tool": self.name,
            "command": json.dumps(arguments, indent=2, ensure_ascii=False),
            "reason": f"{server} isn't a trusted MCP server and this tool can change things",
        }
        return ask(request, get_runtime(Context).context)

    async def _call(self, arguments: dict[str, Any]) -> Output:
        server = self.connection.server.name
        try:
            return await self._output(await self._call_once(arguments))
        except MCPError as e:
            return f"Error from {server}: {e}", []
        except NotConnectedError as e:
            return f"{server} isn't connected: {e}", []
        except ConnectionLostError as e:
            return await self._after_lost(arguments, str(e))

    async def _after_lost(self, arguments: dict[str, Any], error: str) -> Output:
        """Only a read-only call is safe to repeat: a write may already have happened."""
        server = self.connection.server.name
        if not self.read_only:
            uncertain = (
                f"Outcome uncertain: the connection to {server} dropped during the call ({error}). "
                "Check whether it took effect before calling it again."
            )
            return uncertain, []
        if not await self.connection.reconnected(_RECONNECT_SECONDS):
            return f"{server} is unreachable: {error}", []
        try:
            return await self._output(await self._call_once(arguments))
        except (MCPError, NotConnectedError, ConnectionLostError) as e:
            return f"Error from {server}: {e}", []

    async def _call_once(self, arguments: dict[str, Any]) -> CallToolResult:
        """The call names its conversation, for background work it starts (core/mcp/background.py)."""
        return await self.connection.call(self.remote_name, arguments, origin=current_origin())

    async def _output(self, result: CallToolResult) -> Output:
        media = [block for block in result.content if isinstance(block, ImageContent | AudioContent)]
        blocks = [await self.media.block(block, self.name) for block in media]
        references = [block for block in blocks if is_reference(block)]
        return _content(render(result), [block for block in blocks if not is_reference(block)]), references


def render(result: CallToolResult) -> str:
    """The text the model gets for a tool result. Images and audio are left to `ToolMedia`."""
    parts = [_block_text(block) for block in result.content if not isinstance(block, ImageContent | AudioContent)]
    if not parts and result.structured_content is not None:
        parts = [json.dumps(result.structured_content, ensure_ascii=False)]
    text = _truncate(strip_hidden("\n".join(parts)))
    return f"Error: {text}" if result.is_error else text


def _block_text(block: ContentBlock) -> str:
    if isinstance(block, TextContent):
        return block.text
    if isinstance(block, EmbeddedResource):
        resource = block.resource
        return resource.text if isinstance(resource, TextResourceContents) else f"[file {resource.uri} not shown]"
    if isinstance(block, ResourceLink):
        return f"[resource {block.uri}]"
    return f"[{block.type} not shown]"


def _truncate(text: str) -> str:
    limit = settings.mcp_max_output
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n[cut: {len(text) - limit} more characters]"


def _content(text: str, transcripts: list[Block]) -> str | list[Block]:
    """The result's text, followed by the transcripts of its audio."""
    if not transcripts:
        return text
    return [*([{"type": "text", "text": text}] if text else []), *transcripts]
