from db.core import DB_PATH
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

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

    def list_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM characters ORDER BY id").fetchall()
        return [r["id"] for r in rows]

    def get_characters_json(self, char_id) -> str:
        """Return a JSON string containing a list of all characters."""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM characters WHERE id = {char_id}").fetchall()

        character_sheet = []
        for row in rows:
            char = dict(row)
            
            for field in JSON_FIELDS:
                if field in char and char[field] is not None:
                    try:
                        char[field] = json.loads(char[field])
                    except json.JSONDecodeError:
                        pass 
                        
            character_sheet.append(char)

        return json.dumps(character_sheet, indent=2)

    def delete(self, character_id: str) -> bool:
        """Return True if a row was actually deleted."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM characters WHERE id = ?",
                (character_id.strip(),),
            )
        return cur.rowcount > 0