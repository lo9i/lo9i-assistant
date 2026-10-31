"""MCP tools as LangChain tools: approval on untrusted servers and for the tools a plugin says ask first,
a retry only where it's safe, what the server asks during a call answered by the user or the model (answers.py),
and results cleaned and cut to size. Images and audio in results are saved, not put in the checkpoint
(core/mcp/media.py). The tools lo9i adds for a server's resources and prompts (listings.py) run the same way."""

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
from assistant.core.mcp import listings
from assistant.core.mcp.answers import RunAnswers
from assistant.core.mcp.connection import ConnectionLostError, McpConnection, NotConnectedError
from assistant.core.mcp.media import ToolMedia
from assistant.core.mcp.sampling import Sampler
from assistant.core.mcp.servers import McpServer
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
    # Writes what the server asks the model for (sampling.py); None where nothing may.
    sampler: Sampler | None = Field(default=None, exclude=True)
    remote_name: str
    # Annotations are hints a server could lie about: on an untrusted server, a false read-only
    # claim can at most skip approval for that tool.
    read_only: bool = False
    trusted: bool = False
    # Its plugin asks for approval before each call, trusted or not (McpServer.approve).
    asks_first: bool = False

    def _run(self, *args: Any, **kwargs: Any) -> Output:
        raise NotImplementedError("MCP tools only run async.")

    async def _arun(self, **arguments: Any) -> Output:
        rejection = self._approve(arguments)
        if rejection:
            return rejection, []
        return await self._call(arguments)

    def _approve(self, arguments: dict[str, Any]) -> str | None:
        reason = self._approval_reason()
        if reason is None:
            return None
        request = {
            "tool": self.name,
            "command": json.dumps(arguments, indent=2, ensure_ascii=False),
            "reason": reason,
        }
        return ask(request, get_runtime(Context).context)

    def _approval_reason(self) -> str | None:
        server = self.connection.server.name
        if self.asks_first:
            return f"{server} asks for approval each time this tool runs"
        if self.trusted or self.read_only:
            return None
        return f"{server} isn't a trusted MCP server and this tool can change things"

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
        asker = run_answers(self.connection.server, self.sampler)
        return await self.connection.call(self.remote_name, arguments, origin=current_origin(), asker=asker)

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


class McpListingTool(BaseTool):
    """One of the tools lo9i adds for a server's resources and prompts (listings.py), under the name the model
    sees. They only read."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    response_format: Literal["content", "content_and_artifact"] = "content_and_artifact"
    connection: McpConnection = Field(exclude=True)
    media: ToolMedia = Field(exclude=True)
    sampler: Sampler | None = Field(default=None, exclude=True)
    remote_name: str
    read_only: bool = True

    def _run(self, *args: Any, **kwargs: Any) -> Output:
        raise NotImplementedError("MCP tools only run async.")

    async def _arun(self, **arguments: Any) -> Output:
        server = self.connection.server.name
        try:
            return await self._listed(arguments)
        except MCPError as e:
            return f"Error from {server}: {e}", []
        except (NotConnectedError, ConnectionLostError) as e:
            return f"{server} isn't connected: {e}", []

    async def _listed(self, arguments: dict[str, Any]) -> Output:
        match self.remote_name:
            case listings.LIST_RESOURCES:
                return listings.resources_text(*await self.connection.list_resources()), []
            case listings.READ_RESOURCE:
                return await self._read(str(arguments.get("uri", "")))
            case listings.LIST_PROMPTS:
                return listings.prompts_text(await self.connection.list_prompts()), []
            case _:
                prompt = await self.connection.get_prompt(
                    str(arguments.get("name", "")), _arguments(arguments.get("arguments")), self._asker()
                )
                return listings.prompt_text(prompt), []

    async def _read(self, uri: str) -> Output:
        texts, media = listings.resource_parts(await self.connection.read_resource(uri, self._asker()))
        blocks = [await self.media.block(block, self.name) for block in media]
        references = [block for block in blocks if is_reference(block)]
        text = listings.cut("\n\n".join(texts))
        return _content(text, [block for block in blocks if not is_reference(block)]), references

    def _asker(self) -> RunAnswers | None:
        return run_answers(self.connection.server, self.sampler)


def run_answers(server: McpServer, sampler: Sampler | None) -> RunAnswers | None:
    """Who answers what the server asks during a call in this run; None outside a run, where nobody is asked."""
    runtime = get_runtime(Context)
    return RunAnswers(server, runtime.context, sampler) if runtime is not None else None


def _arguments(given: Any) -> dict[str, str]:
    return {str(k): str(v) for k, v in given.items()} if isinstance(given, dict) else {}
