"""Initiative-order endpoints: GET/POST /api/initiative. State lives on app.state."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from engine.core import Initiative

router = APIRouter()


class InitiativePayload(BaseModel):
    enabled: bool
    order: list[str]


@router.get("/api/initiative")
def get_initiative(request: Request) -> dict:
    init = request.app.state.initiative
    return {"enabled": init.enabled, "order": list(init.order)}


@router.post("/api/initiative")
def set_initiative(payload: InitiativePayload, request: Request) -> dict:
    ctx = request.app.state.ctx
    party = list(ctx.party_ids)
    submitted = [cid.strip() for cid in payload.order if cid and cid.strip()]

    if len(submitted) != len(set(submitted)):
        raise HTTPException(status_code=400, detail={"error": "duplicate ids in order"})
    unknown = [cid for cid in submitted if cid not in party]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown character(s)", "unknown": unknown},
        )
    missing = [cid for cid in party if cid not in submitted]
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"error": "order must include every current party member", "missing": missing},
        )

    request.app.state.initiative = Initiative(enabled=payload.enabled, order=submitted)
    return {"enabled": payload.enabled, "order": submitted}
