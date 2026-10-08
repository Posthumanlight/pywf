"""FastAPI frontend for pywf. Serves a one-page chat UI and a small JSON API."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore
from pydantic import BaseModel

from agent.core.agent import MODEL
from api.characters import router as characters_router
from api.lorebook import router as lorebook_router
from api.pages import chat_page, landing_page, memory_page
from api.party import router as party_router
from api.srd import router as srd_router
from db.characters import CharacterRepository
from db.core import DB_PATH
from engine.core import (
    MissingCharactersError,
    PartyContext,
    UnknownTargetError,
    build_party,
    parse_dm_line,
    party_memory_stats,
    run_round,
)
from lorebook.loader import Lorebook, LorebookValidationError, load as load_lorebook
from lorebook.models import BookSettings
from settings.settings import settings

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    dm: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SqliteSaver.from_conn_string(str(DB_PATH)) as saver, SqliteStore.from_conn_string(str(DB_PATH)) as store:
        store.setup()
        app.state.saver = saver
        app.state.store = store
        timeout = settings.model_timeout_s
        app.state.chat_model = init_chat_model(MODEL, timeout=timeout)
        mem_id = settings.memory_model or MODEL
        app.state.memory_model = (
            app.state.chat_model if mem_id == MODEL else init_chat_model(mem_id, timeout=timeout)
        )
        app.state.fallback_models = [init_chat_model(f, timeout=timeout) for f in settings.fallbacks]
        app.state.agent_cache: dict = {}

        lore_path = settings.BASE_PATH / "data" / "lore"
        try:
            app.state.lorebook = load_lorebook(lore_path)
            logger.info("lorebook: loaded %d entries from %s", len(app.state.lorebook.entries), lore_path)
        except (FileNotFoundError, NotADirectoryError, LorebookValidationError) as exc:
            logger.warning("lorebook: load failed (%s); starting with empty book", exc)
            app.state.lorebook = Lorebook(path=lore_path, entries={}, settings=BookSettings())

        try:
            app.state.ctx = build_party(
                saver, store,
                chat_model=app.state.chat_model,
                memory_model=app.state.memory_model,
                fallback_models=app.state.fallback_models,
                agent_cache=app.state.agent_cache,
                lorebook=app.state.lorebook,
            )
        except (MissingCharactersError, ValueError):
            # Tolerate a bad / empty env default so the chat picker can bootstrap the party.
            app.state.ctx = PartyContext(agents={}, names={}, party_ids=[], store=store)
        yield


app = FastAPI(title="pywf", lifespan=lifespan)
app.include_router(characters_router)
app.include_router(party_router)
app.include_router(srd_router)
app.include_router(lorebook_router)


def _ctx(app: FastAPI) -> PartyContext:
    return app.state.ctx


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    ctx = _ctx(app)
    return landing_page(
        party=[{"id": cid, "name": ctx.names[cid]} for cid in ctx.party_ids],
        character_count=len(CharacterRepository().list_summaries()),
        memory=party_memory_stats(ctx),
    )


@app.get("/chat", response_class=HTMLResponse)
def chat_html() -> str:
    return chat_page()


@app.get("/memory", response_class=HTMLResponse)
def memory_html() -> str:
    return memory_page(party_memory_stats(_ctx(app)))


@app.get("/party")
def party() -> dict:
    ctx = _ctx(app)
    return {"party": [{"id": cid, "name": ctx.names[cid]} for cid in ctx.party_ids]}


@app.get("/api/memory")
def api_memory() -> dict:
    return {"party": party_memory_stats(_ctx(app))}


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    ctx = _ctx(app)
    if not ctx.party_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no party selected", "action": "POST /api/party to set one"},
        )
    if not req.dm or not req.dm.strip():
        raise HTTPException(status_code=400, detail="empty dm")
    try:
        parsed = parse_dm_line(req.dm, ctx.party_ids)
    except UnknownTargetError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown party member", "target": exc.target, "party": exc.party_ids},
        )
    turns = run_round(ctx, parsed.dm_text, parsed.order)
    return {"order": parsed.order, "turns": turns}
