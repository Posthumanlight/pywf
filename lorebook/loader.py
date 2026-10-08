"""Load lorebook entries from a directory of .md / .yaml files."""
import re
from pathlib import Path
from typing import Iterable

import yaml
from pydantic import ValidationError

from db.characters import CharacterRepository
from lorebook.matcher import Matcher
from lorebook.models import BookSettings, Entry, Visibility

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

# Files we never treat as entries even when they live in the lore dir.
_SKIP_FILENAMES = {"README.md", "_book.yaml"}


class LorebookValidationError(Exception):
    """Raised when the lorebook directory is malformed. `errors` holds the per-item messages."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors) if errors else "lorebook invalid")
        self.errors = errors


class Lorebook:
    """In-memory lorebook: entries + settings + matcher. Mutable via `reload()`."""

    def __init__(self, path: Path, entries: dict[str, Entry], settings: BookSettings) -> None:
        self.path = path
        self.entries = entries
        self.settings = settings
        self.matcher = Matcher(entries.values(), settings)

    def reload(self) -> None:
        """Re-read `self.path` and swap `self.entries`, `self.settings`, `self.matcher` in place.

        Raises `LorebookValidationError` without touching current state if the new
        directory is invalid.
        """
        new = _read_dir(self.path)
        self.entries = new.entries
        self.settings = new.settings
        self.matcher = new.matcher


def load(path: Path) -> Lorebook:
    """Load every `.md`/`.yaml` under `path` into a `Lorebook`. Raises on validation issues."""
    return _read_dir(path)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _read_dir(path: Path) -> Lorebook:
    if not path.exists():
        raise FileNotFoundError(f"lorebook path not found: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"lorebook path is not a directory: {path}")

    settings = _read_settings(path / "_book.yaml")

    entries: dict[str, Entry] = {}
    errors: list[str] = []
    for file_path in sorted(path.iterdir()):
        if file_path.name in _SKIP_FILENAMES or file_path.name.startswith("."):
            continue
        if file_path.suffix.lower() not in {".md", ".yaml", ".yml"}:
            continue
        try:
            entry = _parse_file(file_path)
        except (LorebookValidationError, ValidationError, yaml.YAMLError) as exc:
            errors.append(f"{file_path.name}: {exc}")
            continue

        if not entry.content.strip():
            errors.append(f"{file_path.name}: empty content")
            continue
        if entry.id in entries:
            errors.append(f"{file_path.name}: duplicate id {entry.id!r} (also in {entries[entry.id].title or entry.id})")
            continue

        entry.token_count = (len(entry.content) + 3) // 4
        entries[entry.id] = entry

    errors.extend(_validate_visibility(entries.values()))
    if errors:
        raise LorebookValidationError(errors)

    return Lorebook(path=path, entries=entries, settings=settings)


def _read_settings(path: Path) -> BookSettings:
    if not path.exists():
        return BookSettings()
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return BookSettings(**data)


def _parse_file(path: Path) -> Entry:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".md":
        match = _FRONTMATTER_RE.match(text)
        if not match:
            raise LorebookValidationError([f"{path.name}: missing YAML frontmatter"])
        front_raw, body = match.group(1), match.group(2)
        front = yaml.safe_load(front_raw) or {}
        if not isinstance(front, dict):
            raise LorebookValidationError([f"{path.name}: frontmatter must be a YAML mapping"])
        front["content"] = body.rstrip() + "\n"
    else:
        front = yaml.safe_load(text) or {}
        if not isinstance(front, dict):
            raise LorebookValidationError([f"{path.name}: YAML must be a mapping"])
    return Entry(**front)


def _validate_visibility(entries: Iterable[Entry]) -> list[str]:
    """Entries using `visibility: [cid, ...]` must only reference known characters."""
    list_vis = [e for e in entries if isinstance(e.visibility, list)]
    if not list_vis:
        return []
    known = set(CharacterRepository().list_ids())
    errors: list[str] = []
    for entry in list_vis:
        missing = [cid for cid in entry.visibility if cid not in known]
        if missing:
            errors.append(f"{entry.id}: visibility references unknown character(s) {missing}")
    return errors
