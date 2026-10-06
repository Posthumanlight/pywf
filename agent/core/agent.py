from langchain.agents import create_agent
from agent.tools.srd_rules_retriever import rules_srd_retriever
from agent.tools.roll_dice import roll_dice
from data.prompts.system_prompt import player_agent_system_prompt

player_agent = create_agent(
    model="google_genai:gemini-3.7-flash",
    tools=[rules_srd_retriever, roll_dice],
    system_prompt=player_agent_system_prompt
)

