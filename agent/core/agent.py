from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware

from agent.tools.get_character_sheet import get_character_sheet
from agent.tools.roll_dice import roll_dice
from agent.tools.srd_rules_retriever import rules_srd_retriever
from data.prompts.system_prompt import build_player_system_prompt


def build_player_agent(
    character_id: str,
    party_member_names: list[str] | None = None,
    checkpointer=None,
    model_fallbacks: list[str] | None = None,
):
    middleware = []
    if model_fallbacks:
        middleware.append(ModelFallbackMiddleware(model_fallbacks[0], *model_fallbacks[1:]))
    return create_agent(
        model="google_genai:gemini-3.7-flash",
        tools=[rules_srd_retriever, roll_dice, get_character_sheet],
        system_prompt=build_player_system_prompt(character_id, party_member_names),
        checkpointer=checkpointer,
        middleware=middleware,
    )
