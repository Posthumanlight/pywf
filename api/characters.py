"""Character CRUD routes: JSON API under /api/characters, HTML pages under /characters."""
import json

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import HTMLResponse

from api.pages import character_form_page, characters_list_page
from db.characters import Character, CharacterRepository

router = APIRouter()


@router.get("/api/characters")
def api_list() -> dict:
    return {"items": CharacterRepository().list_summaries()}


@router.post("/api/characters", status_code=status.HTTP_201_CREATED)
def api_create(character: Character) -> dict:
    repo = CharacterRepository()
    if character.id in repo.list_ids():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "character id already exists", "id": character.id},
        )
    char_id = repo.upsert(character)
    return {"id": char_id, "name": character.name or char_id}


@router.get("/api/characters/{character_id}")
def api_get(character_id: str) -> dict:
    raw = CharacterRepository().get_characters_json(character_id)
    if raw is None:
        raise HTTPException(status_code=404, detail={"error": "not found", "id": character_id})
    return json.loads(raw)


@router.put("/api/characters/{character_id}")
def api_update(character_id: str, character: Character) -> dict:
    if character.id != character_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "id mismatch", "path": character_id, "body": character.id},
        )
    repo = CharacterRepository()
    if character_id not in repo.list_ids():
        raise HTTPException(status_code=404, detail={"error": "not found", "id": character_id})
    repo.upsert(character)
    return {"id": character_id, "name": character.name or character_id}


@router.delete("/api/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete(character_id: str) -> Response:
    repo = CharacterRepository()
    deleted = repo.delete(character_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"error": "not found", "id": character_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/characters", response_class=HTMLResponse)
def page_list() -> str:
    return characters_list_page(CharacterRepository().list_summaries())


@router.get("/characters/new", response_class=HTMLResponse)
def page_new() -> str:
    return character_form_page(mode="new")


@router.get("/characters/{character_id}/edit", response_class=HTMLResponse)
def page_edit(character_id: str) -> str:
    raw = CharacterRepository().get_characters_json(character_id)
    if raw is None:
        raise HTTPException(status_code=404, detail={"error": "not found", "id": character_id})
    return character_form_page(mode="edit", initial=json.loads(raw))
