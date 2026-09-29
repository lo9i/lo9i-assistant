from langgraph.graph.state import CompiledStateGraph

from assistant.core.memory import Memory


class ServiceBase:
    """State shared by the service mixins. Set by `AssistantService.__init__`."""

    _memory: Memory
    _graph: CompiledStateGraph
