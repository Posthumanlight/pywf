"""Long-term memory for player agents.

Short-term memory is the LangGraph thread (SqliteSaver, thread_id == character_id).
It grows by one DM prompt ("round") per invoke, plus the agent's replies and tool calls.

Long-term memory lives in a LangGraph store under the namespace ("memories", <character_id>):
  - "episode:<ns timestamp>" -- summary of a block of archived rounds
  - "chronicle"               -- one rolling digest that older episodes get folded into

`MemoryMiddleware` does two things:
  1. before_agent: when the thread holds more than `trigger_rounds` rounds, everything but the
     last `keep_rounds` rounds is summarized into a new episode and removed from the thread.
     When episodes exceed `max_episodes`, the oldest ones are folded into the chronicle.
  2. wrap_model_call: appends the chronicle and episodes to the system prompt on every model call.

Each agent's thread only contains what its character witnessed (the DM prompts it received,
the turns it was shown, its own replies), so summaries stay in that character's point of view.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse
from langchain.chat_models import BaseChatModel, init_chat_model
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore

logger = logging.getLogger(__name__)

CHRONICLE_KEY = "chronicle"
EPISODE_PREFIX = "episode:"

# Tool outputs that are re-fetchable and only bloat a summary.
_SKIPPED_TOOLS = {"get_character_sheet", "rules_srd_retriever"}

EPISODE_PROMPT = """You maintain the long-term memory of the D&D player character `{character_id}`.
Below is a transcript of several rounds of play, as seen from that character's seat at the table:
"TABLE" lines are what the DM (and the other players' turns, as relayed) said; "ME" lines are
`{character_id}`'s own replies; "DICE" lines are roll results.

Write memory notes the character can rely on in future sessions. Rules:
- Only record what this character witnessed, was told, or did. Facts the DM stated are canon.
- Do not record outcomes the DM never confirmed; mark them as attempted/unresolved instead.
- Be concrete: names, places, numbers, items, promises, debts, threats.
- Skip moment-to-moment chatter and rules lookups.
- Keep it under {max_words} words. Use these sections, writing "None" if empty:

## Events
## People & creatures (name — who they are — attitude toward me/the party)
## Places
## Items, resources & changes to my character
## Party relationships
## Open threads (quests, promises, unanswered questions, plans)
## Table agreements (OOC rulings, house rules, Lines/Veils, safety requests — keep verbatim intent)

<transcript>
{transcript}
</transcript>"""

CHRONICLE_PROMPT = """You maintain the long-term memory of the D&D player character `{character_id}`.
Merge the existing chronicle and the newer episode notes below into ONE updated chronicle.
- Keep it under {max_words} words, using the same section headings as the episode notes.
- Newer information wins over older information when they conflict.
- Compress finished storylines to a line each; keep open threads, named NPCs, owed debts,
  and every table agreement (rulings, Lines/Veils, safety requests) intact.

<existing_chronicle>
{chronicle}
</existing_chronicle>

<newer_episodes>
{episodes}
</newer_episodes>"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def memory_namespace(character_id: str) -> tuple[str, str]:
    return ("memories", character_id)


def _round_starts(messages: list[AnyMessage]) -> list[int]:
    """Indices of HumanMessages — each one is a DM prompt, i.e. the start of a round."""
    return [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]


def format_transcript(messages: list[AnyMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            lines.append(f"TABLE: {m.text}")
        elif isinstance(m, AIMessage):
            if m.text.strip():
                lines.append(f"ME: {m.text}")
        elif isinstance(m, ToolMessage):
            if m.name not in _SKIPPED_TOOLS:
                lines.append(f"DICE: {m.text}" if m.name == "roll_dice" else f"TOOL {m.name}: {m.text}")
    return "\n\n".join(lines)


def load_memories(store: BaseStore, character_id: str) -> tuple[dict | None, list[dict]]:
    """Return (chronicle value or None, episode values oldest-first)."""
    ns = memory_namespace(character_id)
    chronicle = store.get(ns, CHRONICLE_KEY)
    items = store.search(ns, limit=1000)
    episodes = sorted(
        (it for it in items if it.key.startswith(EPISODE_PREFIX)),
        key=lambda it: it.key,
    )
    return (chronicle.value if chronicle else None), [{"key": it.key, **it.value} for it in episodes]


def render_memory_block(chronicle: dict | None, episodes: list[dict]) -> str:
    if not chronicle and not episodes:
        return ""
    parts = [
        "============================================================",
        "YOUR MEMORIES (from earlier sessions — what your character remembers)",
        "============================================================",
        "These are your character's recollections, oldest first. Treat them as what you know, "
        "not as new DM narration. If a memory conflicts with what the DM says now, the DM wins.",
    ]
    if chronicle:
        parts += ["", "### Chronicle (the long story so far)", chronicle["text"]]
    for i, ep in enumerate(episodes, 1):
        parts += ["", f"### Recent episode {i} of {len(episodes)}", ep["text"]]
    return "\n".join(parts)


class MemoryMiddleware(AgentMiddleware):
    """Archive old rounds into a store-backed long-term memory and inject it into the prompt."""

    def __init__(
        self,
        character_id: str,
        model: str | BaseChatModel,
        *,
        trigger_rounds: int = 30,
        keep_rounds: int = 10,
        max_episodes: int = 6,
        episode_words: int = 400,
        chronicle_words: int = 1200,
    ) -> None:
        super().__init__()
        if keep_rounds < 1 or trigger_rounds <= keep_rounds:
            raise ValueError("need 1 <= keep_rounds < trigger_rounds")
        self.character_id = character_id
        self.model = init_chat_model(model) if isinstance(model, str) else model
        self.trigger_rounds = trigger_rounds
        self.keep_rounds = keep_rounds
        self.max_episodes = max_episodes
        self.episode_words = episode_words
        self.chronicle_words = chronicle_words

    # ---------- archiving ----------

    def before_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        store = runtime.store
        if store is None:
            return None
        messages = state["messages"]
        starts = _round_starts(messages)
        if len(starts) <= self.trigger_rounds:
            return None

        # Cut at the start of a round, so AI tool calls and their ToolMessages are never split.
        cutoff = starts[-self.keep_rounds]
        old = messages[:cutoff]
        archived_rounds = len(starts) - self.keep_rounds
        try:
            self._write_episode(store, old, archived_rounds)
            self._fold_old_episodes(store)
        except Exception:
            # Never lose the turn over a memory failure; the thread is left intact and we retry next round.
            logger.exception("memory: summarization failed for %s; will retry next round", self.character_id)
            return None

        logger.info("memory: archived %d rounds (%d messages) for %s", archived_rounds, len(old), self.character_id)
        return {"messages": [RemoveMessage(id=m.id) for m in old if m.id]}

    def _summarize(self, prompt: str) -> str:
        return self.model.invoke([HumanMessage(content=prompt)]).text.strip()

    def _write_episode(self, store: BaseStore, old: list[AnyMessage], rounds: int) -> None:
        text = self._summarize(EPISODE_PROMPT.format(
            character_id=self.character_id,
            max_words=self.episode_words,
            transcript=format_transcript(old),
        ))
        store.put(
            memory_namespace(self.character_id),
            f"{EPISODE_PREFIX}{time.time_ns():020d}",
            {"text": text, "rounds": rounds, "created_at": _now_iso()},
        )

    def _fold_old_episodes(self, store: BaseStore) -> None:
        chronicle, episodes = load_memories(store, self.character_id)
        if len(episodes) <= self.max_episodes:
            return
        # Fold the oldest half so folding doesn't run on every new episode.
        to_fold = episodes[: len(episodes) - self.max_episodes // 2]
        text = self._summarize(CHRONICLE_PROMPT.format(
            character_id=self.character_id,
            max_words=self.chronicle_words,
            chronicle=chronicle["text"] if chronicle else "None yet.",
            episodes="\n\n---\n\n".join(ep["text"] for ep in to_fold),
        ))
        ns = memory_namespace(self.character_id)
        store.put(ns, CHRONICLE_KEY, {
            "text": text,
            "rounds": (chronicle or {}).get("rounds", 0) + sum(ep["rounds"] for ep in to_fold),
            "updated_at": _now_iso(),
        })
        for ep in to_fold:
            store.delete(ns, ep["key"])

    # ---------- recall ----------

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        store = request.runtime.store if request.runtime else None
        if store is None:
            return handler(request)
        block = render_memory_block(*load_memories(store, self.character_id))
        if not block:
            return handler(request)
        base = request.system_message.text if request.system_message else ""
        return handler(request.override(system_message=SystemMessage(content=f"{base}\n\n{block}")))


def memory_stats(agent: Any, store: BaseStore | None, character_id: str, trigger_rounds: int) -> dict:
    """Counts for one character: what's in the live thread vs. what's archived."""
    state = agent.get_state({"configurable": {"thread_id": character_id}})
    messages = state.values.get("messages", []) if state else []
    rounds = len(_round_starts(messages))
    stats = {
        "character_id": character_id,
        "thread_messages": len(messages),
        "thread_rounds": rounds,
        "replies_in_thread": sum(1 for m in messages if isinstance(m, AIMessage) and m.text.strip()),
        "rounds_until_archive": max(trigger_rounds + 1 - rounds, 0),
        "episodes": 0,
        "archived_rounds": 0,
        "has_chronicle": False,
    }
    if store is not None:
        chronicle, episodes = load_memories(store, character_id)
        stats["episodes"] = len(episodes)
        stats["has_chronicle"] = chronicle is not None
        stats["archived_rounds"] = (chronicle or {}).get("rounds", 0) + sum(ep["rounds"] for ep in episodes)
    return stats
