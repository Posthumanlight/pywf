"""FastAPI frontend for pywf. Serves a one-page chat UI and a small JSON API."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore
from pydantic import BaseModel

from api.characters import router as characters_router
from api.pages import chat_page, landing_page, memory_page
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


class ChatRequest(BaseModel):
    dm: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SqliteSaver.from_conn_string(str(DB_PATH)) as saver, SqliteStore.from_conn_string(str(DB_PATH)) as store:
        store.setup()
        try:
            ctx = build_party(saver, store)
        except MissingCharactersError as exc:
            raise RuntimeError(
                f"{exc} Available ids: {exc.available}. "
                "Seed one with: poetry run python scripts/seed_character.py <path-to-json>"
            ) from exc
        app.state.ctx = ctx
        yield


app = FastAPI(title="pywf", lifespan=lifespan)
app.include_router(characters_router)


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
