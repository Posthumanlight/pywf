"""Lorebook introspection + hot-reload endpoints."""
from fastapi import APIRouter, HTTPException, Request

from lorebook.loader import LorebookValidationError
from lorebook.models import Visibility

router = APIRouter()


@router.get("/api/lorebook")
def get_lorebook(request: Request) -> dict:
    book = request.app.state.lorebook
    entries = [
        {
            "id": e.id,
            "title": e.title,
            "keys_count": len(e.keys) + len(e.key_regex),
            "token_count": e.token_count,
            "position": e.position.value,
            "constant": e.constant,
            "priority": e.priority,
            "visibility": (
                e.visibility.value if isinstance(e.visibility, Visibility) else list(e.visibility)
            ),
        }
        for e in book.entries.values()
    ]
    return {
        "path": str(book.path),
        "settings": book.settings.model_dump(),
        "entries": entries,
    }


@router.post("/api/lorebook/reload")
def reload_lorebook(request: Request) -> dict:
    book = request.app.state.lorebook
    try:
        book.reload()
    except LorebookValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid lorebook", "errors": exc.errors})
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail={"error": "lorebook path missing", "message": str(exc)})
    return {"entries": len(book.entries)}
