"""SQLite-backed storage for lorebook entries and book-level settings."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from db.core import DB_PATH
from lorebook.models import BookSettings, Entry, Logic, Position, Visibility


_SCHEMA = """
CREATE TABLE IF NOT EXISTS lorebook_entries (
    id                            TEXT PRIMARY KEY,
    title                         TEXT NOT NULL DEFAULT '',
    keys_json                     TEXT NOT NULL DEFAULT '[]',
    key_regex_json                TEXT NOT NULL DEFAULT '[]',
    secondary_keys_json           TEXT NOT NULL DEFAULT '[]',
    secondary_logic               TEXT NOT NULL DEFAULT 'and_any',
    constant                      INTEGER NOT NULL DEFAULT 0,
    priority                      INTEGER NOT NULL DEFAULT 0,
    position                      TEXT NOT NULL DEFAULT 'after',
    no_recurse_into               INTEGER NOT NULL DEFAULT 0,
    not_triggerable_by_recursion  INTEGER NOT NULL DEFAULT 0,
    visibility_json               TEXT NOT NULL DEFAULT '"global"',
    content                       TEXT NOT NULL,
    token_count                   INTEGER NOT NULL DEFAULT 0,
    created_at                    TEXT NOT NULL,
    updated_at                    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lorebook_settings (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    scan_depth        INTEGER NOT NULL DEFAULT 1,
    token_budget      INTEGER NOT NULL DEFAULT 2000,
    max_recursion     INTEGER NOT NULL DEFAULT 3,
    case_sensitive    INTEGER NOT NULL DEFAULT 0,
    whole_word        INTEGER NOT NULL DEFAULT 1,
    normalize_unicode INTEGER NOT NULL DEFAULT 1
);

INSERT OR IGNORE INTO lorebook_settings (id) VALUES (1);
"""


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _row_to_entry(row: sqlite3.Row) -> Entry:
    visibility_raw = json.loads(row["visibility_json"])
    if isinstance(visibility_raw, str):
        visibility = Visibility(visibility_raw)
    else:
        visibility = list(visibility_raw)
    return Entry(
        id=row["id"],
        title=row["title"] or "",
        keys=json.loads(row["keys_json"]),
        key_regex=json.loads(row["key_regex_json"]),
        secondary_keys=json.loads(row["secondary_keys_json"]),
        secondary_logic=Logic(row["secondary_logic"]),
        constant=bool(row["constant"]),
        priority=row["priority"],
        position=Position(row["position"]),
        no_recurse_into=bool(row["no_recurse_into"]),
        not_triggerable_by_recursion=bool(row["not_triggerable_by_recursion"]),
        visibility=visibility,
        content=row["content"],
        token_count=row["token_count"],
    )


def _entry_to_params(entry: Entry, now: str) -> dict:
    visibility_json = (
        json.dumps(entry.visibility.value)
        if isinstance(entry.visibility, Visibility)
        else json.dumps(list(entry.visibility))
    )
    return {
        "id": entry.id,
        "title": entry.title,
        "keys_json": json.dumps(entry.keys, ensure_ascii=False),
        "key_regex_json": json.dumps(entry.key_regex, ensure_ascii=False),
        "secondary_keys_json": json.dumps(entry.secondary_keys, ensure_ascii=False),
        "secondary_logic": entry.secondary_logic.value,
        "constant": int(entry.constant),
        "priority": entry.priority,
        "position": entry.position.value,
        "no_recurse_into": int(entry.no_recurse_into),
        "not_triggerable_by_recursion": int(entry.not_triggerable_by_recursion),
        "visibility_json": visibility_json,
        "content": entry.content,
        "token_count": (len(entry.content) + 3) // 4,
        "now": now,
    }


_UPSERT_SQL = """
INSERT INTO lorebook_entries (
    id, title, keys_json, key_regex_json, secondary_keys_json, secondary_logic,
    constant, priority, position, no_recurse_into, not_triggerable_by_recursion,
    visibility_json, content, token_count, created_at, updated_at
) VALUES (
    :id, :title, :keys_json, :key_regex_json, :secondary_keys_json, :secondary_logic,
    :constant, :priority, :position, :no_recurse_into, :not_triggerable_by_recursion,
    :visibility_json, :content, :token_count, :now, :now
)
ON CONFLICT(id) DO UPDATE SET
    title = excluded.title,
    keys_json = excluded.keys_json,
    key_regex_json = excluded.key_regex_json,
    secondary_keys_json = excluded.secondary_keys_json,
    secondary_logic = excluded.secondary_logic,
    constant = excluded.constant,
    priority = excluded.priority,
    position = excluded.position,
    no_recurse_into = excluded.no_recurse_into,
    not_triggerable_by_recursion = excluded.not_triggerable_by_recursion,
    visibility_json = excluded.visibility_json,
    content = excluded.content,
    token_count = excluded.token_count,
    updated_at = excluded.updated_at
"""


class LorebookRepository:
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
            conn.executescript(_SCHEMA)

    # ---- entries ---------------------------------------------------------

    def list_summaries(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, keys_json, key_regex_json, position, priority, constant, token_count "
                "FROM lorebook_entries ORDER BY -priority, id"
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            out.append({
                "id": r["id"],
                "title": r["title"] or "",
                "keys_count": len(json.loads(r["keys_json"])) + len(json.loads(r["key_regex_json"])),
                "position": r["position"],
                "priority": r["priority"],
                "constant": bool(r["constant"]),
                "token_count": r["token_count"],
            })
        return out

    def list_entries(self) -> list[Entry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM lorebook_entries ORDER BY -priority, id"
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def get(self, entry_id: str) -> Entry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lorebook_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        return _row_to_entry(row) if row else None

    def exists(self, entry_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM lorebook_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        return row is not None

    def upsert(self, entry: Entry) -> None:
        if not entry.content.strip():
            raise ValueError("empty content")
        with self._connect() as conn:
            conn.execute(_UPSERT_SQL, _entry_to_params(entry, _now_iso()))

    def delete(self, entry_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM lorebook_entries WHERE id = ?",
                (entry_id,),
            )
        return cur.rowcount > 0

    # ---- settings --------------------------------------------------------

    def get_settings(self) -> BookSettings:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT scan_depth, token_budget, max_recursion, case_sensitive, whole_word, normalize_unicode "
                "FROM lorebook_settings WHERE id = 1"
            ).fetchone()
        if row is None:
            return BookSettings()
        return BookSettings(
            scan_depth=row["scan_depth"],
            token_budget=row["token_budget"],
            max_recursion=row["max_recursion"],
            case_sensitive=bool(row["case_sensitive"]),
            whole_word=bool(row["whole_word"]),
            normalize_unicode=bool(row["normalize_unicode"]),
        )

    def update_settings(self, settings: BookSettings) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE lorebook_settings SET "
                "scan_depth = :scan_depth, token_budget = :token_budget, "
                "max_recursion = :max_recursion, case_sensitive = :case_sensitive, "
                "whole_word = :whole_word, normalize_unicode = :normalize_unicode "
                "WHERE id = 1",
                {
                    "scan_depth": settings.scan_depth,
                    "token_budget": settings.token_budget,
                    "max_recursion": settings.max_recursion,
                    "case_sensitive": int(settings.case_sensitive),
                    "whole_word": int(settings.whole_word),
                    "normalize_unicode": int(settings.normalize_unicode),
                },
            )
