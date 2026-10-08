"""ModelFallbackMiddleware with structured logging + per-model cooldown awareness.

The middleware builds a unified candidate list `[primary, *fallbacks]` on every
call. Models currently on cooldown are skipped; the first successful call wins.
Exceptions classified as rate-limit / quota errors by `cooldown.is_quota_error`
trigger a cooldown via `cooldown.start_cooldown`, so subsequent requests go
straight to the next non-cooled candidate.

The sanitizer step from langchain's `ModelFallbackMiddleware` (Anthropic cache
marker stripping) is skipped because every model in this project is Gemini or
OpenAI-compatible via OpenRouter. If a non-Gemini / non-OpenRouter provider is
ever added, this should inherit the parent's `_sanitize_request_for_fallback`
call.
"""
import logging
from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.errors import GraphBubbleUp

from agent.core.cooldown import is_on_cooldown, is_quota_error, spec_for, start_cooldown

logger = logging.getLogger("pywf.fallback")
cooldown_logger = logging.getLogger("pywf.cooldown")


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
        candidates: list[tuple[str, BaseChatModel]] = [("primary", request.model)]
        candidates.extend((f"fallback[{i}]", m) for i, m in enumerate(self.fallbacks))

        last_exc: Exception | None = None
        tried = 0

        for label, model in candidates:
            if is_on_cooldown(model):
                cooldown_logger.info(
                    "cooldown/%s: skipping %s (%s)",
                    self.character_id, label, spec_for(model) or type(model).__name__,
                )
                continue

            tried += 1
            attempt = request if label == "primary" else request.override(model=model)
            if label != "primary":
                logger.info(
                    "fallback/%s: trying %s %s",
                    self.character_id, label, type(model).__name__,
                )

            try:
                return handler(attempt)
            except GraphBubbleUp:
                raise
            except Exception as e:
                if is_quota_error(e):
                    seconds = start_cooldown(model, e)
                    logger.warning(
                        "fallback/%s: %s hit quota (%s); cooling %ss",
                        self.character_id, label, type(e).__name__, seconds,
                    )
                else:
                    logger.warning(
                        "fallback/%s: %s failed: %s: %s",
                        self.character_id, label, type(e).__name__, e,
                    )
                last_exc = e

        if tried == 0:
            cooldown_logger.error(
                "cooldown/%s: all %d candidate(s) on cooldown",
                self.character_id, len(candidates),
            )
            raise RuntimeError("all models on cooldown")

        logger.error(
            "fallback/%s: exhausted %d candidate(s) (%d tried)",
            self.character_id, len(candidates), tried,
        )
        assert last_exc is not None
        raise last_exc
