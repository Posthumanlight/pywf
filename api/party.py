"""Runtime party selection: let the client swap `app.state.ctx` on demand."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.characters import CharacterRepository
from engine.core import Initiative, build_party, reconcile_initiative

router = APIRouter()


class PartyRequest(BaseModel):
    character_ids: list[str]


@router.post("/api/party")
def set_party(req: PartyRequest, request: Request) -> dict:
    ids = [cid.strip() for cid in req.character_ids if cid and cid.strip()]
    if not ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "empty party", "message": "pick at least one character"},
        )
    available = set(CharacterRepository().list_ids())
    missing = [cid for cid in ids if cid not in available]
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown character(s)", "missing": missing, "available": sorted(available)},
        )
    app = request.app
    ctx = build_party(
        app.state.saver, app.state.store, party_ids=ids,
        chat_model=app.state.chat_model,
        memory_model=app.state.memory_model,
        fallback_models=app.state.fallback_models,
        agent_cache=app.state.agent_cache,
        lorebook=app.state.lorebook,
    )
    app.state.ctx = ctx
    old = app.state.initiative
    app.state.initiative = Initiative(
        enabled=old.enabled,
        order=reconcile_initiative(old.order, ctx.party_ids),
    )
    return {"party": [{"id": cid, "name": ctx.names[cid]} for cid in ctx.party_ids]}
