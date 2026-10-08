"""Load the lorebook from SQLite into an in-memory `Lorebook` plus matcher."""
from typing import Iterable

from db.characters import CharacterRepository
from db.lorebook import LorebookRepository
from lorebook.matcher import Matcher
from lorebook.models import BookSettings, Entry


class LorebookValidationError(Exception):
    """Raised when authored data is malformed. `errors` holds per-item messages."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors) if errors else "lorebook invalid")
        self.errors = errors


class Lorebook:
    """In-memory lorebook backed by SQLite. Mutable via `refresh()`."""

    def __init__(self, entries: dict[str, Entry], settings: BookSettings) -> None:
        self.entries = entries
        self.settings = settings
        self.matcher = Matcher(entries.values(), settings)

    def refresh(self) -> None:
        """Re-read entries + settings from the DB and rebuild the matcher in place."""
        new = _read_from_db()
        self.entries = new.entries
        self.settings = new.settings
        self.matcher = new.matcher


def load() -> Lorebook:
    """Build a `Lorebook` from the SQLite tables. Does not validate visibility — do that at write time."""
    return _read_from_db()


def validate_visibility(entry: Entry) -> list[str]:
    """Return a list of error messages (empty if visibility is OK).

    Used by write-path routes to reject entries whose visibility list points at
    characters that aren't in the DB. Kept out of the repository so db/ doesn't
    depend on db/characters.
    """
    if not isinstance(entry.visibility, list):
        return []
    known = set(CharacterRepository().list_ids())
    missing = [cid for cid in entry.visibility if cid not in known]
    if missing:
        return [f"{entry.id}: visibility references unknown character(s) {missing}"]
    return []


# ---------------------------------------------------------------------------


def _read_from_db() -> Lorebook:
    repo = LorebookRepository()
    entries_list = repo.list_entries()
    settings = repo.get_settings()
    entries = {e.id: e for e in entries_list}
    return Lorebook(entries=entries, settings=settings)
