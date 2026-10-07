"""On-demand SRD/homebrew body lookup for the character-form rules panel."""
from fastapi import APIRouter, HTTPException

from data.srd_catalog import get_body

router = APIRouter()

_CATEGORIES = {"class", "subclass", "species", "feat", "spell"}


@router.get("/api/srd/{category}/{name}")
def api_srd(category: str, name: str) -> dict:
    if category not in _CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown category", "category": category, "valid": sorted(_CATEGORIES)},
        )
    body = get_body(category, name)
    if body is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not found", "category": category, "name": name},
        )
    return {"category": category, "name": name, "body": body}
