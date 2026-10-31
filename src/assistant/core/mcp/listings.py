"""Tools lo9i adds to an MCP server for what it has besides tools: its resources (files, records it offers to read,
by URI) and its prompts (texts it fills in with arguments). A server that has them gets `list_resources` and
`read_resource`, or `list_prompts` and `get_prompt`, listed with its tools and kept with them (tool_cache.py), each
marked as added (ADDED in its `_meta`). The agent gets them only once the user turns them on for the server
(McpServer.resources, McpServer.prompts), and the apps show them as those switches rather than as tools. They only
read, so they need no approval. A server that asks something while reading (asking.py) is answered as for a call.
A tool of the server's own with one of these names comes first; the added one is then left out."""

from typing import Any

from mcp import Client
from mcp.types import (
    AudioContent,
    BlobResourceContents,
    EmbeddedResource,
    GetPromptResult,
    ImageContent,
    Prompt,
    ReadResourceResult,
    Resource,
    ResourceTemplate,
    ServerCapabilities,
    TextContent,
    TextResourceContents,
    Tool,
    ToolAnnotations,
)

from assistant.core.config import settings
from assistant.core.hidden_text import strip_hidden
from assistant.core.mcp.servers import McpServer

ADDED = "lo9i/added"
RESOURCES, PROMPTS = "resources", "prompts"
LIST_RESOURCES, READ_RESOURCE = "list_resources", "read_resource"
LIST_PROMPTS, GET_PROMPT = "list_prompts", "get_prompt"
# Entries listed at most: past that, a list says how many it left out.
_LISTED = 200


def added(capabilities: ServerCapabilities | None) -> list[Tool]:
    """The tools for what the server says it has."""
    if capabilities is None:
        return []
    return [*(_RESOURCE_TOOLS if capabilities.resources else []), *(_PROMPT_TOOLS if capabilities.prompts else [])]


def kind(tool: Tool) -> str | None:
    """resources or prompts for a tool lo9i added, None for the server's own."""
    found = (tool.meta or {}).get(ADDED)
    return found if found in (RESOURCES, PROMPTS) else None


def turned_on(server: McpServer, tool: Tool) -> bool:
    return (kind(tool) == RESOURCES and server.resources) or (kind(tool) == PROMPTS and server.prompts)


def offers(tools: list[Tool]) -> list[str]:
    """What the server has besides tools, from the tools lo9i added for it."""
    return sorted({k for t in tools if (k := kind(t))})


def _tool(name: str, description: str, added_for: str, properties: dict[str, Any], required: list[str]) -> Tool:
    schema = {"type": "object", "properties": properties, "required": required}
    return Tool(
        name=name,
        description=description,
        input_schema=schema,
        annotations=ToolAnnotations(read_only_hint=True),
        _meta={ADDED: added_for},
    )


_RESOURCE_TOOLS = [
    _tool(
        LIST_RESOURCES,
        "List the resources this server offers to read, and the URI templates it reads.",
        RESOURCES,
        {},
        [],
    ),
    _tool(
        READ_RESOURCE,
        "Read one of this server's resources by its URI (from list_resources, or a template filled in).",
        RESOURCES,
        {"uri": {"type": "string", "description": "The resource's URI."}},
        ["uri"],
    ),
]
_PROMPT_TOOLS = [
    _tool(LIST_PROMPTS, "List the prompts this server offers, with their arguments.", PROMPTS, {}, []),
    _tool(
        GET_PROMPT,
        "Get one of this server's prompts, filled in with its arguments, to follow it.",
        PROMPTS,
        {
            "name": {"type": "string", "description": "The prompt's name, from list_prompts."},
            "arguments": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "Its arguments by name, as text.",
            },
        },
        ["name"],
    ),
]


async def all_resources(client: Client) -> list[Resource]:
    found: list[Resource] = []
    cursor: str | None = None
    while len(found) <= _LISTED:
        page = await client.list_resources(cursor=cursor)
        found += page.resources
        if not (cursor := page.next_cursor):
            break
    return found


async def all_templates(client: Client) -> list[ResourceTemplate]:
    found: list[ResourceTemplate] = []
    cursor: str | None = None
    while len(found) <= _LISTED:
        page = await client.list_resource_templates(cursor=cursor)
        found += page.resource_templates
        if not (cursor := page.next_cursor):
            break
    return found


async def all_prompts(client: Client) -> list[Prompt]:
    found: list[Prompt] = []
    cursor: str | None = None
    while len(found) <= _LISTED:
        page = await client.list_prompts(cursor=cursor)
        found += page.prompts
        if not (cursor := page.next_cursor):
            break
    return found


def resources_text(resources: list[Resource], templates: list[ResourceTemplate]) -> str:
    lines = [_resource_line(r.uri, r.name, r.title, r.description, r.mime_type) for r in resources[:_LISTED]]
    lines += [
        _resource_line(t.uri_template, t.name, t.title, t.description, t.mime_type, template=True)
        for t in templates[:_LISTED]
    ]
    left = max(len(resources) - _LISTED, 0) + max(len(templates) - _LISTED, 0)
    return cut("\n".join(lines) + (f"\n[{left} more not listed]" if left else "") or "No resources.")


def prompts_text(prompts: list[Prompt]) -> str:
    lines = [_prompt_line(p) for p in prompts[:_LISTED]]
    left = max(len(prompts) - _LISTED, 0)
    return cut("\n".join(lines) + (f"\n[{left} more not listed]" if left else "") or "No prompts.")


def prompt_text(prompt: GetPromptResult) -> str:
    parts = [f"{prompt.description}\n" if prompt.description else ""]
    parts += [f"[{m.role}] {_content_text(m.content)}" for m in prompt.messages]
    return cut("\n\n".join(p for p in parts if p))


def resource_parts(result: ReadResourceResult) -> tuple[list[str], list[ImageContent | AudioContent]]:
    """The text of each part, and its images and sound, which ToolMedia saves."""
    texts: list[str] = []
    media: list[ImageContent | AudioContent] = []
    for part in result.contents:
        if isinstance(part, TextResourceContents):
            texts.append(part.text)
        elif isinstance(part, BlobResourceContents) and (found := _blob_media(part)) is not None:
            media.append(found)
        else:
            texts.append(f"[{part.mime_type or 'binary'} content of {part.uri} not shown]")
    return texts, media


def _blob_media(part: BlobResourceContents) -> ImageContent | AudioContent | None:
    mime = part.mime_type or ""
    if mime.startswith("image/"):
        return ImageContent(type="image", data=part.blob, mime_type=mime)
    if mime.startswith("audio/"):
        return AudioContent(type="audio", data=part.blob, mime_type=mime)
    return None


def _resource_line(
    uri: str, name: str, title: str | None, description: str | None, mime: str | None, template: bool = False
) -> str:
    kind_of = "template " if template else ""
    about = f" — {description}" if description else ""
    return strip_hidden(f"- {kind_of}{uri} ({mime or 'unknown type'}): {title or name}{about}")


def _prompt_line(prompt: Prompt) -> str:
    arguments = ", ".join(f"{a.name}{'*' if a.required else ''}" for a in prompt.arguments or [])
    about = f": {prompt.description}" if prompt.description else ""
    return strip_hidden(f"- {prompt.name}({arguments}){about}")


def _content_text(content: Any) -> str:
    if isinstance(content, TextContent):
        return content.text
    if isinstance(content, EmbeddedResource) and isinstance(content.resource, TextResourceContents):
        return content.resource.text
    return f"[{getattr(content, 'type', 'content')} not shown]"


def cut(text: str) -> str:
    text = strip_hidden(text)
    limit = settings.mcp_max_output
    return text if len(text) <= limit else f"{text[:limit]}\n[cut: {len(text) - limit} more characters]"
