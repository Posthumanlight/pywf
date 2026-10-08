from langchain.agents import create_agent
from langchain.chat_models import BaseChatModel, init_chat_model

from agent.core.fallback import LoggingModelFallbackMiddleware
from agent.core.memory import MemoryMiddleware
from agent.tools.get_character_sheet import get_character_sheet
from agent.tools.roll_dice import roll_dice
from agent.tools.srd_rules_retriever import rules_srd_retriever
from data.prompts.system_prompt import build_player_system_prompt
from lorebook import LorebookMiddleware
from settings.settings import settings

MODEL = "google_genai:gemini-3.7-flash"


def build_player_agent(
    character_id: str,
    party_member_names: list[str] | None = None,
    checkpointer=None,
    model_fallbacks: list[str] | None = None,
    store=None,
    chat_model: BaseChatModel | None = None,
    memory_model: BaseChatModel | None = None,
    fallback_models: list[BaseChatModel] | None = None,
    lorebook=None,
):
    timeout = settings.model_timeout_s

    # CLI path: no pre-built chat model → build one with a deadline so hung Gemini
    # calls bubble up to the fallback middleware instead of blocking forever.
    if chat_model is None:
        chat_model = init_chat_model(MODEL, timeout=timeout)

    # Fallbacks: pre-built list wins; else build each from the string list with the same timeout.
    if fallback_models:
        fallbacks: list[BaseChatModel] = fallback_models
    elif model_fallbacks:
        fallbacks = [init_chat_model(name, timeout=timeout) for name in model_fallbacks]
    else:
        fallbacks = []

    middleware = []
    if store is not None:
        mem = memory_model or chat_model
        middleware.append(MemoryMiddleware(
            character_id,
            model=mem,
            trigger_rounds=settings.memory_trigger_rounds,
            keep_rounds=settings.memory_keep_rounds,
            max_episodes=settings.memory_max_episodes,
        ))
    if lorebook is not None:
        middleware.append(LorebookMiddleware(character_id, lorebook))
    if fallbacks:
        middleware.append(LoggingModelFallbackMiddleware(character_id, fallbacks))
    return create_agent(
        model=chat_model,
        tools=[rules_srd_retriever, roll_dice, get_character_sheet],
        system_prompt=build_player_system_prompt(character_id, party_member_names),
        checkpointer=checkpointer,
        store=store,
        middleware=middleware,
    )
