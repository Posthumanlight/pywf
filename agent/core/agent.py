from langchain.agents import create_agent

from agent.tools.get_character_sheet import get_character_sheet
from agent.tools.roll_dice import roll_dice
from agent.tools.srd_rules_retriever import rules_srd_retriever
from data.prompts.system_prompt import build_player_system_prompt


def build_player_agent(character_id: str, checkpointer=None):
    return create_agent(
        model="google_genai:gemini-3.7-flash",
        tools=[rules_srd_retriever, roll_dice, get_character_sheet],
        system_prompt=build_player_system_prompt(character_id),
        checkpointer=checkpointer,
    )
