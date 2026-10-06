import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, ConfigDict, Field

from db.core import DB_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

SCALAR_FIELDS = (
    "name", "species", "background", "alignment", "origin_feat",
    "armor_class", "current_hp", "max_hp", "temporary_hp",
    "speed_ft", "initiative_bonus", "proficiency_bonus", "notes",
)

JSON_FIELDS = (
    "classes", "abilities", "feats",
    "saving_throw_proficiencies", "skill_proficiencies",
    "languages", "senses", "equipment", "features",
    "spells", "spell_slots", "resources", "conditions",
)


class Character(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str

    name: str | None = None
    species: str | None = None
    background: str | None = None
    alignment: str | None = None
    origin_feat: str | None = None
    armor_class: int | None = None
    current_hp: int | None = None
    max_hp: int | None = None
    temporary_hp: int | None = None
    speed_ft: int | None = None
    initiative_bonus: int | None = None
    proficiency_bonus: int | None = None
    notes: str = ""

    classes: list[dict] = Field(default_factory=list)
    abilities: dict = Field(default_factory=dict)
    feats: list[dict] = Field(default_factory=list)
    saving_throw_proficiencies: list[str] = Field(default_factory=list)
    skill_proficiencies: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    senses: dict = Field(default_factory=dict)
    equipment: list[dict] = Field(default_factory=list)
    features: list[dict] = Field(default_factory=list)
    spells: list[dict] = Field(default_factory=list)
    spell_slots: dict = Field(default_factory=dict)
    resources: dict = Field(default_factory=dict)
    conditions: list[str] = Field(default_factory=list)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id                          TEXT PRIMARY KEY,
    name                        TEXT NOT NULL,
    species                     TEXT,
    background                  TEXT,
    alignment                   TEXT,
    origin_feat                 TEXT,
    armor_class                 INTEGER,
    current_hp                  INTEGER,
    max_hp                      INTEGER,
    temporary_hp                INTEGER,
    speed_ft                    INTEGER,
    initiative_bonus            INTEGER,
    proficiency_bonus           INTEGER,
    notes                       TEXT NOT NULL DEFAULT '',

    classes                     TEXT NOT NULL,
    abilities                   TEXT NOT NULL,
    feats                       TEXT NOT NULL,
    saving_throw_proficiencies  TEXT NOT NULL,
    skill_proficiencies         TEXT NOT NULL,
    languages                   TEXT NOT NULL,
    senses                      TEXT NOT NULL,
    equipment                   TEXT NOT NULL,
    features                    TEXT NOT NULL,
    spells                      TEXT NOT NULL,
    spell_slots                 TEXT NOT NULL,
    resources                   TEXT NOT NULL,
    conditions                  TEXT NOT NULL,

    created_at                  TEXT NOT NULL,
    updated_at                  TEXT NOT NULL
);
"""

_COLUMNS = ("id", *SCALAR_FIELDS, *JSON_FIELDS)

_UPSERT_SQL = f"""
INSERT INTO characters ({", ".join(_COLUMNS)}, created_at, updated_at)
VALUES ({", ".join(f":{c}" for c in _COLUMNS)}, :now, :now)
ON CONFLICT(id) DO UPDATE SET
    {", ".join(f"{c} = excluded.{c}" for c in _COLUMNS if c != "id")},
    updated_at = excluded.updated_at
"""

class CharacterRepository:

    def __init__(self, db_path: str | Path = DB_PATH) -> None:
        self.db_path = str(db_path)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)

    def upsert(self, character: Character) -> str:
        """Insert a new character or partially update an existing one.

        New id: all unset fields fall back to `Character` defaults, row is inserted.
        Existing id: only fields explicitly set on `character` are written; others are preserved.
        """
        provided: dict[str, Any] = character.model_dump(exclude_unset=True)
        char_id = character.id
        provided.pop("id", None)

        for field in JSON_FIELDS:
            if field in provided:
                provided[field] = json.dumps(provided[field], ensure_ascii=False)

        now = _now_iso()
        writable = set(SCALAR_FIELDS) | set(JSON_FIELDS)

        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM characters WHERE id = ?",
                (char_id,),
            ).fetchone() is not None

            if not exists:
                full = character.model_dump()
                full.update({k: provided[k] for k in provided})
                for field in JSON_FIELDS:
                    if not isinstance(full[field], str):
                        full[field] = json.dumps(full[field], ensure_ascii=False)
                conn.execute(_UPSERT_SQL, {**full, "now": now})
                return char_id

            if not provided:
                return char_id

            unknown = set(provided) - writable
            if unknown:
                raise ValueError(f"Unknown character fields: {sorted(unknown)}")

            set_clause = ", ".join(f"{col} = :{col}" for col in provided)
            conn.execute(
                f"UPDATE characters SET {set_clause}, updated_at = :now WHERE id = :id",
                {**provided, "id": char_id, "now": now},
            )
        return char_id

    def list_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM characters ORDER BY id").fetchall()
        return [r["id"] for r in rows]

    def get_characters_json(self, char_id: str) -> str | None:
        """Return the JSON-encoded character sheet for `char_id`, or `None` if no such character exists."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM characters WHERE id = ?",
                (char_id,),
            ).fetchone()

        if row is None:
            return None

        char = dict(row)
        for field in JSON_FIELDS:
            if field in char and char[field] is not None:
                try:
                    char[field] = json.loads(char[field])
                except json.JSONDecodeError:
                    pass

        return json.dumps(char, indent=2, ensure_ascii=False)

    def delete(self, character_id: str) -> bool:
        """Return True if a row was actually deleted."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM characters WHERE id = ?",
                (character_id.strip(),),
            )
        return cur.rowcount > 0