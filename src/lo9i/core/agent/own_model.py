"""The model a conversation answers with, for clients: which it is, the models it can change to, and changing it
(core/conversation/own_model.py)."""

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig

from lo9i.core import checkpoints
from lo9i.core.agent.locking import LockingMixin
from lo9i.core.agent.threads import ConversationBusyError
from lo9i.core.conversation import own_model
from lo9i.core.conversation.own_model import OwnModel
from lo9i.core.i18n import message, said
from lo9i.core.llm.listing import ModelListError, ModelOption, available
from lo9i.core.to_the_end import to_the_end


class ModelChangeError(Exception):
    """The model isn't one the conversation can change to, or the provider couldn't say which those are."""


@dataclass
class ConversationModel:
    # The model's id, and the name its provider lists it with.
    model: str
    name: str
    # It's the main model (Settings → Model): none was picked for the conversation.
    main: bool


class OwnModelMixin(LockingMixin):
    async def conversation_model(self, user_id: str, thread_id: str) -> ConversationModel:
        own = await own_model.load(self._storage.store, user_id, thread_id)
        if own is None or own.provider != self._model.provider:
            return ConversationModel(self._model.model, self._model.model, main=True)
        return ConversationModel(own.model, own.name, main=False)

    async def conversation_models(self) -> list[ModelOption]:
        """The models a conversation can answer with: those the main model's provider lists for its key, else the
        main and worker models. Raises ModelChangeError."""
        try:
            listed = await available(self._model.provider, self._model.values)
        except ModelListError as e:
            raise ModelChangeError(message(e)) from e
        return listed or [ModelOption(m, m) for m in dict.fromkeys([self._model.model, self._model.worker_model])]

    async def set_conversation_model(self, user_id: str, thread_id: str, model: str) -> ConversationModel:
        """`model`: one of `conversation_models`; "" or the main model's id goes back to the main model. In a
        conversation with messages, a note marks the change, and from the next message the model gets a summary of
        what came before instead of the messages. Raises ModelChangeError, and ConversationBusyError while a reply
        runs there or waits for the user's answer."""
        own = await self._own_model(model)
        if thread_id in self._active_runs:
            raise ConversationBusyError(said("A reply is running in this conversation. Change the model once it ends."))
        before = await self.conversation_model(user_id, thread_id)
        async with self._thread_lock(thread_id):
            noted = await self._mark_model_change(thread_id, before, own)
            await own_model.save(self._storage.store, user_id, thread_id, own)
        changed = await self.conversation_model(user_id, thread_id)
        # `noted`: the conversation shows the note now, naming the model.
        self.bus.publish("conversation_model", thread_id=thread_id, noted=noted, name=changed.name)
        return changed

    async def _own_model(self, model: str) -> OwnModel | None:
        if not model or model == self._model.model:
            return None
        found = next((m for m in await self.conversation_models() if m.id == model), None)
        if found is None:
            raise ModelChangeError(said("{model} isn't a model this conversation can answer with.", model=model))
        return OwnModel(self._model.provider, found.id, found.name)

    async def _mark_model_change(self, thread_id: str, before: ConversationModel, own: OwnModel | None) -> bool:
        """Appends the note, in a conversation with messages, when the model changes; refused while its run waits
        for the user's answer: written then, it would end the run that waits. Returns whether it appended it."""
        after = own.model if own is not None else self._model.model
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        state = await self._graph.aget_state(config)
        if after == before.model or not state.values.get("messages"):
            return False
        if state.next:
            raise ConversationBusyError(said("This conversation waits for your answer. Answer it first."))
        mark = own_model.mark(own.name if own is not None else self._model.model)
        await to_the_end(self._graph.aupdate_state(config, {"messages": [mark]}, as_node="agent"))
        await checkpoints.prune(self._storage.checkpointer, thread_id)
        return True
