import asyncio

from assistant.core.bus import EventBus
from assistant.core.conversation.digest import Digester
from assistant.core.graph import Graph
from assistant.core.outbox import Outbox
from assistant.core.speech.transcriber import Transcriber
from assistant.core.storage import Storage


class ServiceBase:
    """State shared by the service mixins. Set by `AssistantService.__init__`."""

    _storage: Storage
    bus: EventBus
    # Channel adapters register here to deliver messages the agent starts (core/outbox.py).
    outbox: Outbox
    _graph: Graph
    _transcriber: Transcriber
    _digester: Digester
    # Background work (archiving) kept referenced until it finishes.
    _background: set[asyncio.Task]
