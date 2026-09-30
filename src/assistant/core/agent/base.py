from langgraph.graph.state import CompiledStateGraph

from assistant.core.speech.transcriber import Transcriber
from assistant.core.storage import Storage


class ServiceBase:
    """State shared by the service mixins. Set by `AssistantService.__init__`."""

    _storage: Storage
    _graph: CompiledStateGraph
    _transcriber: Transcriber
