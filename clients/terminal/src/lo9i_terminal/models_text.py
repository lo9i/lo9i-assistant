"""The models a conversation can answer with, as /use lists them to pick from."""

from lo9i.client.daemon_client.conversations import ConversationModels
from lo9i.core.agent import ConversationModel
from lo9i_terminal.i18n import t


def model_lines(offered: ConversationModels, current: ConversationModel) -> dict[str, str]:
    """Each line and the model it picks ("" for the main model, which the conversation follows when it changes): the
    main model first, then the others, the one the conversation answers with marked."""
    main = next((m.name for m in offered.models if m.id == offered.main), offered.main)
    lines = {_marked(t("{model} (main model)", model=main), current.main): ""}
    for model in offered.models:
        if model.id != offered.main:
            label = model.name if model.name == model.id else f"{model.name} · {model.id}"
            lines[_marked(label, not current.main and model.id == current.model)] = model.id
    return lines


def _marked(label: str, current: bool) -> str:
    return f"● {label}" if current else f"  {label}"
