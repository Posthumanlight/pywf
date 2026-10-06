"""pywf CLI: a human DM converses with a single bound AI player agent."""
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver

from agent.core.agent import build_player_agent
from db.characters import CharacterRepository
from db.core import DB_PATH
from settings.settings import settings


def _print_banner(character_id: str) -> None:
    print(f"pywf — playing as '{character_id}'")
    print("Type DM narration / direct address. Mark your OOC lines with [OOC: ...].")
    print("Commands: /exit, /quit")
    print()


def _render_response(result: dict) -> str:
    messages = result.get("messages", [])
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if content and getattr(msg, "type", None) == "ai":
            if isinstance(content, str):
                return content
            parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            return "".join(parts).strip() or str(content)
    return "(no response)"


def main() -> int:
    character_id = settings.character_id

    available = CharacterRepository().list_ids()
    if character_id not in available:
        print(f"character_id '{character_id}' not found in the DB.")
        print(f"available ids: {available}")
        print("Seed one with: poetry run python scripts/seed_character.py <path-to-json>")
        return 1

    with SqliteSaver.from_conn_string(str(DB_PATH)) as saver:
        agent = build_player_agent(character_id, checkpointer=saver)
        config: RunnableConfig = {"configurable": {"thread_id": character_id}}

        _print_banner(character_id)

        while True:
            try:
                line = input("DM> ")
            except (EOFError, KeyboardInterrupt):
                print()
                return 0

            prompt = line.strip()
            if not prompt:
                continue
            if prompt.lower() in ("/exit", "/quit"):
                return 0

            result = agent.invoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config=config,
            )
            print()
            print(_render_response(result))
            print()


if __name__ == "__main__":
    raise SystemExit(main())
