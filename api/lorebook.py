"""Lorebook CRUD routes: JSON API under /api/lorebook/*, HTML pages under /lorebook/*."""
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse

from api.pages import lorebook_form_page, lorebook_list_page
from db.characters import CharacterRepository
from db.lorebook import LorebookRepository
from lorebook.loader import validate_visibility
from lorebook.models import BookSettings, Entry

router = APIRouter()


def _refresh(request: Request) -> None:
    """Rebuild the in-memory lorebook so cached agents see the new state next turn."""
    request.app.state.lorebook.refresh()


# ---- entry CRUD ------------------------------------------------------------


@router.get("/api/lorebook")
def api_overview() -> dict:
    repo = LorebookRepository()
    return {
        "settings": repo.get_settings().model_dump(),
        "entries": repo.list_summaries(),
    }


@router.get("/api/lorebook/entries")
def api_entries_list() -> dict:
    return {"items": LorebookRepository().list_summaries()}


@router.post("/api/lorebook/entries", status_code=status.HTTP_201_CREATED)
def api_entry_create(entry: Entry, request: Request) -> dict:
    repo = LorebookRepository()
    if repo.exists(entry.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "entry id already exists", "id": entry.id},
        )
    errors = validate_visibility(entry)
    if errors:
        raise HTTPException(status_code=400, detail={"error": "invalid visibility", "errors": errors})
    repo.upsert(entry)
    _refresh(request)
    return {"id": entry.id, "title": entry.title}


@router.get("/api/lorebook/entries/{entry_id}")
def api_entry_get(entry_id: str) -> dict:
    entry = LorebookRepository().get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail={"error": "not found", "id": entry_id})
    return entry.model_dump()


@router.put("/api/lorebook/entries/{entry_id}")
def api_entry_update(entry_id: str, entry: Entry, request: Request) -> dict:
    if entry.id != entry_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "id mismatch", "path": entry_id, "body": entry.id},
        )
    repo = LorebookRepository()
    if not repo.exists(entry_id):
        raise HTTPException(status_code=404, detail={"error": "not found", "id": entry_id})
    errors = validate_visibility(entry)
    if errors:
        raise HTTPException(status_code=400, detail={"error": "invalid visibility", "errors": errors})
    repo.upsert(entry)
    _refresh(request)
    return {"id": entry.id, "title": entry.title}


@router.delete("/api/lorebook/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_entry_delete(entry_id: str, request: Request) -> Response:
    repo = LorebookRepository()
    if not repo.delete(entry_id):
        raise HTTPException(status_code=404, detail={"error": "not found", "id": entry_id})
    _refresh(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- settings --------------------------------------------------------------


@router.get("/api/lorebook/settings")
def api_settings_get() -> dict:
    return LorebookRepository().get_settings().model_dump()


@router.put("/api/lorebook/settings")
def api_settings_update(settings: BookSettings, request: Request) -> dict:
    repo = LorebookRepository()
    repo.update_settings(settings)
    _refresh(request)
    return repo.get_settings().model_dump()


# ---- HTML pages ------------------------------------------------------------


@router.get("/lorebook", response_class=HTMLResponse)
def page_list() -> str:
    return lorebook_list_page(LorebookRepository().list_summaries())


@router.get("/lorebook/new", response_class=HTMLResponse)
def page_new() -> str:
    return lorebook_form_page(
        mode="new",
        character_ids=CharacterRepository().list_ids(),
    )


@router.get("/lorebook/{entry_id}/edit", response_class=HTMLResponse)
def page_edit(entry_id: str) -> str:
    entry = LorebookRepository().get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail={"error": "not found", "id": entry_id})
    return lorebook_form_page(
        mode="edit",
        initial=entry.model_dump(),
        character_ids=CharacterRepository().list_ids(),
    )
