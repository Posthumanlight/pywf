"""LorebookMiddleware: run the activation engine on each model call and inject lore."""
import logging
from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage

from lorebook.activation import activate
from lorebook.loader import Lorebook
from lorebook.models import Position

logger = logging.getLogger("pywf.lorebook")


class LorebookMiddleware(AgentMiddleware):
    """Scans the latest HumanMessage, activates matching entries, injects into the system prompt."""

    def __init__(self, character_id: str, book: Lorebook) -> None:
        super().__init__()
        self.character_id = character_id
        self.book = book

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        scan = _latest_human_text(request.messages)
        if not scan:
            logger.debug("lorebook/%s: no scan buffer; passing through", self.character_id)
            return handler(request)

        result = activate(self.book, scan, character_id=self.character_id)
        before = "\n\n".join(e.content for e in result.activated if e.position == Position.BEFORE)
        after = "\n\n".join(e.content for e in result.activated if e.position == Position.AFTER)

        if not (before or after):
            logger.debug("lorebook/%s: no entries fired", self.character_id)
            return handler(request)

        base = request.system_message.text if request.system_message else ""
        new_sys = "\n\n".join(p for p in (before, base, after) if p)

        logger.info(
            "lorebook/%s: fired=%s dropped=%s before_chars=%d after_chars=%d",
            self.character_id,
            [t.entry_id for t in result.trace if t.fired],
            [t.entry_id for t in result.trace if t.dropped_budget],
            len(before),
            len(after),
        )
        return handler(request.override(system_message=SystemMessage(content=new_sys)))


def _latest_human_text(messages: list[AnyMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.text or ""
    return ""
