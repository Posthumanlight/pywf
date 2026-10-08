"""Factory that resolves a model spec string into a `BaseChatModel`.

Standard langchain prefixes (`google_genai:`, `openai:`, ...) flow through
`init_chat_model`. The special `openrouter:` prefix builds a `ChatOpenAI`
pointed at OpenRouter's OpenAI-compatible endpoint.
"""
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from agent.core.cooldown import register_model
from settings.settings import settings

_OPENROUTER_PREFIX = "openrouter:"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def build_chat_model(spec: str, *, timeout: int) -> BaseChatModel:
    """Resolve a model spec string into a ready-to-use chat model.

    - `openrouter:<provider/model>` -> `ChatOpenAI` against the OpenRouter endpoint.
    - Anything else is handed to langchain's `init_chat_model` as-is.
    """
    if spec.startswith(_OPENROUTER_PREFIX):
        model: BaseChatModel = ChatOpenAI(
            model=spec[len(_OPENROUTER_PREFIX):],
            base_url=_OPENROUTER_BASE_URL,
            api_key=settings.openrouter_api_key,
            timeout=timeout,
        )
    else:
        model = init_chat_model(spec, timeout=timeout)
    register_model(model, spec)
    return model
