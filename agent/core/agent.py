from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware

from agent.core.memory import MemoryMiddleware
from agent.tools.get_character_sheet import get_character_sheet
from agent.tools.roll_dice import roll_dice
from agent.tools.srd_rules_retriever import rules_srd_retriever
from data.prompts.system_prompt import build_player_system_prompt
from settings.settings import settings

MODEL = "google_genai:gemini-3.7-flash"


def build_player_agent(
    character_id: str,
    party_member_names: list[str] | None = None,
    checkpointer=None,
    model_fallbacks: list[str] | None = None,
    store=None,
):
    middleware = []
    if store is not None:
        middleware.append(MemoryMiddleware(
            character_id,
            model=settings.memory_model or MODEL,
            trigger_rounds=settings.memory_trigger_rounds,
            keep_rounds=settings.memory_keep_rounds,
            max_episodes=settings.memory_max_episodes,
        ))
    if model_fallbacks:
        middleware.append(ModelFallbackMiddleware(model_fallbacks[0], *model_fallbacks[1:]))
    return create_agent(
        model=MODEL,
        tools=[rules_srd_retriever, roll_dice, get_character_sheet],
        system_prompt=build_player_system_prompt(character_id, party_member_names),
        checkpointer=checkpointer,
        store=store,
        middleware=middleware,
    )
