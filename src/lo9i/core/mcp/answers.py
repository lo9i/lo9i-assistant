"""What the user and the model answer an MCP server during a run's call (asking.py): a form or a link for the user
(elicitation.py), shown like an approval, which pauses the run until they answer; text from the model
(sampling.py), which the user approves first unless the server is trusted. Nobody watches a scheduled run, so there
a form is declined, and text is asked for as approvals are there (core/tools/approval.py). A server asking for its
roots is refused: lo9i gives no folders to servers."""

from langgraph.types import interrupt
from mcp.types import CreateMessageRequest, CreateMessageRequestParams, ElicitRequest, ElicitRequestParams, InputRequest

from lo9i.core.context import Context
from lo9i.core.mcp import elicitation, sampling
from lo9i.core.mcp.asking import Answer, refused
from lo9i.core.mcp.sampling import SAMPLES_PER_HOUR, Sampler
from lo9i.core.mcp.servers import McpServer
from lo9i.core.tools.approval import ask


class RunAnswers:
    def __init__(self, server: McpServer, context: Context, sampler: Sampler | None) -> None:
        self._server = server
        self._context = context
        self._sampler = sampler

    async def answer(self, request: InputRequest) -> Answer:
        match request:
            case ElicitRequest(params=params):
                return self._elicit(params)
            case CreateMessageRequest(params=params):
                return await self._sample(params)
            case _:
                return refused("lo9i gives MCP servers no roots.")

    def _elicit(self, params: ElicitRequestParams) -> Answer:
        form = elicitation.request(self._server.name, params)
        if form is None or self._context.unattended:
            return elicitation.declined()
        return elicitation.result(form, interrupt(form))

    async def _sample(self, params: CreateMessageRequestParams) -> Answer:
        name = self._server.name
        if self._sampler is None:
            return refused("lo9i can't ask the model here.")
        if self._sampler.over_limit(name):
            return refused(f"{name} already had {SAMPLES_PER_HOUR} texts from the model in the last hour.")
        if not self._server.trusted and (rejection := ask(sampling.shown(name, params), self._context)):
            return refused(rejection)
        return await self._sampler.sample(name, params)
