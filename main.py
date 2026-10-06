"""pywf CLI: a human DM converses with a party of AI player agents."""
import json
import random

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver

from agent.core.agent import build_player_agent
from db.characters import CharacterRepository
from db.core import DB_PATH
from settings.settings import settings


def _print_banner(party_ids: list[str], names: dict[str, str]) -> None:
    roster = ", ".join(f"{names[cid]} (@{cid})" for cid in party_ids)
    print(f"pywf — party: {roster}")
    print("Type DM narration / direct address. Mark your OOC lines with [OOC: ...].")
    print("Prefix with @<id> to speak to one party member (e.g. '@thorin ...').")
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


def _assemble_turn_input(
    dm_text: str,
    prior_turns: list[tuple[str, str]],
    speaker_name: str,
) -> str:
    lines: list[str] = []
    if dm_text:
        lines.append(f"DM: {dm_text}")
    if prior_turns:
        lines.append("")
        lines.append("Earlier this round:")
        for name, text in prior_turns:
            lines.append(f"- {name} said: {text}")
    lines.append("")
    lines.append(f"Your turn, {speaker_name}. Respond in character.")
    return "\n".join(lines)


def main() -> int:
    party_ids = list(settings.party)
    if not party_ids:
        print("No character_ids configured. Set character_ids=<id1>,<id2>,... in .env")
        return 1

    repo = CharacterRepository()
    available = set(repo.list_ids())
    missing = [cid for cid in party_ids if cid not in available]
    if missing:
        print(f"Missing character(s) in DB: {missing}")
        print(f"Available ids: {sorted(available)}")
        print("Seed one with: poetry run python scripts/seed_character.py <path-to-json>")
        return 1

    names: dict[str, str] = {}
    for cid in party_ids:
        raw = repo.get_characters_json(cid)
        assert raw is not None, f"preflight passed but {cid} vanished"
        sheet = json.loads(raw)
        names[cid] = sheet.get("name") or cid

    fallbacks = list(settings.fallbacks)

    with SqliteSaver.from_conn_string(str(DB_PATH)) as saver:
        agents = {}
        for cid in party_ids:
            peers = [names[other] for other in party_ids if other != cid]
            agents[cid] = build_player_agent(
                cid,
                party_member_names=peers,
                checkpointer=saver,
                model_fallbacks=fallbacks,
            )

        _print_banner(party_ids, names)

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

            if prompt.startswith("@"):
                head, _, body = prompt.partition(" ")
                target = head[1:]
                if target not in agents:
                    print(f"unknown party member: {target!r}; party: {party_ids}")
                    continue
                order = [target]
                dm_text = body.strip()
            else:
                order = random.sample(party_ids, len(party_ids))
                dm_text = prompt

            prior: list[tuple[str, str]] = []
            for cid in order:
                agent_input = _assemble_turn_input(dm_text, prior, speaker_name=names[cid])
                config: RunnableConfig = {"configurable": {"thread_id": cid}}
                result = agents[cid].invoke(
                    {"messages": [{"role": "user", "content": agent_input}]},
                    config=config,
                )
                reply = _render_response(result)
                print()
                print(f"{names[cid]}> {reply}")
                print()
                prior.append((names[cid], reply))


if __name__ == "__main__":
    raise SystemExit(main())
