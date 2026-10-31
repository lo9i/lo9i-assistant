"""What a server asks the client while it handles a request (MCP's elicitation and sampling): a form for the user to
fill in, or text from the model. An `Asker` answers it; in a run that's `RunAnswers` (answers.py), which pauses the
run for the user, so it answers only in the task of the call the question belongs to.

A server on the 2026-07-28 protocol asks by answering the request with `InputRequiredResult`: the questions, and
state to send back with the answers when the request is made again (`rounds`). A server on an older one sends each
question as a request of its own while the call runs; the client's callbacks get it on the connection's task, and
`InFlight` hands it to the call in progress, whose task answers it (`answering`). A question that comes while no
call, or more than one, is in progress can't be told apart, and is refused.

When answering pauses the run (LangGraph's interrupt), the call is given up and made again from the start once the
user answers: the server asks the same questions again, the ones answered already are answered at once, and work
before them is done again (a sampled text written again)."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterator
from typing import Any, Protocol

from mcp.client.session import ClientRequestContext
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_REQUEST,
    CreateMessageRequest,
    CreateMessageRequestParams,
    ElicitRequest,
    ElicitRequestParams,
    ErrorData,
    InputRequest,
    InputRequiredResult,
    InputResponse,
    InputResponses,
)

# Requests made again with answers before a server's request counts as never ending.
MAX_ROUNDS = 10
# A round with no questions, only state to send back: the server is still working.
_STATE_ONLY_SECONDS = 0.1

Answer = InputResponse | ErrorData


class Asker(Protocol):
    async def answer(self, request: InputRequest) -> Answer:
        """The user's or the model's answer to what the server asks, or an error refusing it. May pause the run
        (LangGraph's interrupt) to ask the user."""
        ...


def refused(text: str) -> ErrorData:
    return ErrorData(code=INVALID_REQUEST, message=text)


async def answer(asker: Asker | None, request: InputRequest) -> Answer:
    """Without an asker (a call not made in a run, such as a conversation handed to a plugin's agent), nothing is
    asked: the server is told it can't be answered here."""
    if asker is None:
        return refused(f"lo9i can't answer {request.method} here: nobody is asked during this call.")
    return await asker.answer(request)


async def rounds[R](
    send: Callable[[InputResponses | None, str | None], Awaitable[R | InputRequiredResult]], asker: Asker | None
) -> R:
    """Makes the request with `send` until the server answers it: each time it asks, its questions are answered one
    after another, in its order (so a paused run asks the same way when it goes on), and the request made again
    with the answers and its state. Raises MCPError when a question is refused, or after MAX_ROUNDS."""
    responses: InputResponses | None = None
    state: str | None = None
    for _ in range(MAX_ROUNDS):
        result = await send(responses, state)
        if not isinstance(result, InputRequiredResult):
            return result
        responses = await _answered(result, asker)
        state = result.request_state
        if responses is None:
            await asyncio.sleep(_STATE_ONLY_SECONDS)
    raise MCPError(INVALID_REQUEST, f"The server asked for more than {MAX_ROUNDS} rounds of answers.")


async def _answered(result: InputRequiredResult, asker: Asker | None) -> InputResponses | None:
    if not result.input_requests:
        return None
    responses: InputResponses = {}
    for key, request in result.input_requests.items():
        given = await answer(asker, request)
        if isinstance(given, ErrorData):
            raise MCPError.from_error_data(given)
        responses[key] = given
    return responses


class _Call:
    """A call in progress, which questions sent apart from it go to."""

    def __init__(self) -> None:
        self.questions: asyncio.Queue[tuple[InputRequest, asyncio.Future[Answer]]] = asyncio.Queue()

    def close(self) -> None:
        """A question it never answered (the run paused, the call ended) is refused."""
        while not self.questions.empty():
            _, waiting = self.questions.get_nowait()
            if not waiting.done():
                waiting.set_result(refused("The call this question belonged to stopped before it was answered."))


class InFlight:
    """A connection's calls in progress, and its callbacks for the questions a server on a protocol before
    2026-07-28 sends while one runs."""

    def __init__(self) -> None:
        self._calls: set[_Call] = set()

    @contextlib.contextmanager
    def call(self) -> Iterator[_Call]:
        made = _Call()
        self._calls.add(made)
        try:
            yield made
        finally:
            self._calls.discard(made)
            made.close()

    async def elicit(self, context: ClientRequestContext, params: ElicitRequestParams) -> Any:
        return await self._ask(ElicitRequest(params=params))

    async def sample(self, context: ClientRequestContext, params: CreateMessageRequestParams) -> Any:
        return await self._ask(CreateMessageRequest(params=params))

    async def _ask(self, request: InputRequest) -> Answer:
        if len(self._calls) != 1:
            return refused("lo9i can't tell which of its calls this question belongs to, so it isn't asked.")
        waiting: asyncio.Future[Answer] = asyncio.get_running_loop().create_future()
        next(iter(self._calls)).questions.put_nowait((request, waiting))
        return await waiting


async def answering[R](work: Awaitable[R], call: _Call, asker: Asker | None) -> R:
    """`work`'s result, answering the questions sent apart from it while it runs. When answering pauses the run,
    the work is given up."""
    running = asyncio.ensure_future(work)
    try:
        while True:
            asked = asyncio.ensure_future(call.questions.get())
            done, _ = await asyncio.wait({running, asked}, return_when=asyncio.FIRST_COMPLETED)
            if asked not in done:
                asked.cancel()
                return running.result()
            await _answer_one(*asked.result(), asker)
    finally:
        if not running.done():
            running.cancel()
            with contextlib.suppress(BaseException):
                await running


async def _answer_one(request: InputRequest, waiting: asyncio.Future[Answer], asker: Asker | None) -> None:
    """A question not answered because the run paused is refused, so the server's request doesn't hang."""
    try:
        waiting.set_result(await answer(asker, request))
    finally:
        if not waiting.done():
            waiting.set_result(refused("The run paused to ask the user; the call will be made again."))
