"""ModelFallbackMiddleware with structured logging per attempt.

Only the primary + fallback switching behavior is reused from langchain's
ModelFallbackMiddleware; the sanitizer step (Anthropic cache marker stripping)
is skipped because every model in this project is Gemini. If a non-Gemini
provider is ever added, this needs to inherit the parent's
_sanitize_request_for_fallback call.
"""
import logging
from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.errors import GraphBubbleUp

logger = logging.getLogger("pywf.fallback")


class LoggingModelFallbackMiddleware(AgentMiddleware):
    """Try primary first; on any exception, iterate fallbacks. Log every attempt."""

    def __init__(self, character_id: str, fallbacks: list[BaseChatModel]) -> None:
        super().__init__()
        self.character_id = character_id
        self.fallbacks = fallbacks

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        last_exc: Exception | None = None
        try:
            return handler(request)
        except GraphBubbleUp:
            raise
        except Exception as e:
            logger.warning(
                "fallback/%s: primary failed: %s: %s",
                self.character_id, type(e).__name__, e,
            )
            last_exc = e

        for i, model in enumerate(self.fallbacks):
            try:
                logger.info(
                    "fallback/%s: trying fallback[%d] %s",
                    self.character_id, i, type(model).__name__,
                )
                return handler(request.override(model=model))
            except GraphBubbleUp:
                raise
            except Exception as e:
                logger.warning(
                    "fallback/%s: fallback[%d] failed: %s: %s",
                    self.character_id, i, type(e).__name__, e,
                )
                last_exc = e

        logger.error(
            "fallback/%s: exhausted %d model(s)",
            self.character_id, len(self.fallbacks) + 1,
        )
        assert last_exc is not None
        raise last_exc
