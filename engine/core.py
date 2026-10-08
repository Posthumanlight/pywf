"""Shared party-execution engine used by both the CLI and the FastAPI frontend."""
import json
import logging
import random
from dataclasses import dataclass
from typing import Any, Sequence, TypedDict

from langchain_core.runnables import RunnableConfig

from agent.core.agent import build_player_agent
from agent.core.memory import memory_stats
from db.characters import CharacterRepository
from settings.settings import settings

logger = logging.getLogger("pywf.engine")


class Turn(TypedDict):
    character_id: str
    name: str
    text: str


@dataclass
class PartyContext:
    agents: dict[str, Any]
    names: dict[str, str]
    party_ids: list[str]
    store: Any = None


@dataclass
class ParsedLine:
    order: list[str]
    dm_text: str


class UnknownTargetError(Exception):
    def __init__(self, target: str, party_ids: Sequence[str]):
        super().__init__(f"unknown party member: {target!r}; party: {list(party_ids)}")
        self.target = target
        self.party_ids = list(party_ids)


class MissingCharactersError(Exception):
    def __init__(self, missing: Sequence[str], available: Sequence[str]):
        super().__init__(f"Missing character(s) in DB: {list(missing)}")
        self.missing = list(missing)
        self.available = list(available)


def build_party(
    saver,
    store=None,
    party_ids=None,
    *,
    chat_model=None,
    memory_model=None,
    fallback_models=None,
    agent_cache: dict | None = None,
    lorebook=None,
) -> PartyContext:
    party_ids = list(party_ids) if party_ids is not None else list(settings.party)
    if not party_ids:
        raise ValueError("No character_ids configured. Set character_ids=<id1>,<id2>,... in .env, or pick a party at /chat.")

    repo = CharacterRepository()
    available = set(repo.list_ids())
    missing = [cid for cid in party_ids if cid not in available]
    if missing:
        raise MissingCharactersError(missing, sorted(available))

    names: dict[str, str] = {}
    for cid in party_ids:
        raw = repo.get_characters_json(cid)
        assert raw is not None, f"preflight passed but {cid} vanished"
        sheet = json.loads(raw)
        names[cid] = sheet.get("name") or cid

    fallbacks_str = list(settings.fallbacks)
    agents: dict[str, Any] = {}
    for cid in party_ids:
        peers = [names[other] for other in party_ids if other != cid]
        cache_key = (cid, frozenset(peers))
        if agent_cache is not None and cache_key in agent_cache:
            agents[cid] = agent_cache[cache_key]
            continue
        agent = build_player_agent(
            cid,
            party_member_names=peers,
            checkpointer=saver,
            model_fallbacks=fallbacks_str,
            store=store,
            chat_model=chat_model,
            memory_model=memory_model,
            fallback_models=fallback_models,
            lorebook=lorebook,
        )
        agents[cid] = agent
        if agent_cache is not None:
            agent_cache[cache_key] = agent

    return PartyContext(agents=agents, names=names, party_ids=party_ids, store=store)


def parse_dm_line(line: str, party_ids: Sequence[str]) -> ParsedLine:
    prompt = line.strip()
    if prompt.startswith("@"):
        head, _, body = prompt.partition(" ")
        target = head[1:]
        if target not in party_ids:
            raise UnknownTargetError(target, party_ids)
        return ParsedLine(order=[target], dm_text=body.strip())
    order = random.sample(list(party_ids), len(party_ids))
    return ParsedLine(order=order, dm_text=prompt)


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


def run_round(ctx: PartyContext, dm_text: str, order: list[str]) -> list[Turn]:
    prior: list[tuple[str, str]] = []
    turns: list[Turn] = []
    for cid in order:
        agent_input = _assemble_turn_input(dm_text, prior, speaker_name=ctx.names[cid])
        config: RunnableConfig = {"configurable": {"thread_id": cid}}
        try:
            result = ctx.agents[cid].invoke(
                {"messages": [{"role": "user", "content": agent_input}]},
                config=config,
            )
            reply = _render_response(result)
        except Exception as exc:
            logger.exception("run_round: %s invoke failed; stopping round", cid)
            turns.append(Turn(
                character_id=cid,
                name=ctx.names[cid],
                text=f"[error: {type(exc).__name__}: {exc}]",
            ))
            break
        turns.append(Turn(character_id=cid, name=ctx.names[cid], text=reply))
        prior.append((ctx.names[cid], reply))
    return turns


def party_memory_stats(ctx: PartyContext) -> list[dict]:
    return [
        {"name": ctx.names[cid], **memory_stats(ctx.agents[cid], ctx.store, cid, settings.memory_trigger_rounds)}
        for cid in ctx.party_ids
    ]
