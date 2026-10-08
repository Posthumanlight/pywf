"""Non-model verification of the lorebook: normalizer, matcher, activation, DB repo, API."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from db.lorebook import LorebookRepository
from lorebook.activation import activate
from lorebook.loader import Lorebook, LorebookValidationError, load, validate_visibility
from lorebook.matcher import Matcher
from lorebook.models import BookSettings, Entry, Logic, Position, Visibility
from lorebook.normalizer import normalize

VERIFY_PREFIX = "__verify_"


def _cleanup_verify_rows() -> None:
    repo = LorebookRepository()
    for s in repo.list_summaries():
        if s["id"].startswith(VERIFY_PREFIX):
            repo.delete(s["id"])


def verify_normalizer() -> None:
    print("--- normalizer ---")
    assert normalize("The Duke OF Veyl", case_sensitive=False, normalize_unicode=True) == "the duke of veyl"
    assert normalize("The Duke OF Veyl", case_sensitive=True, normalize_unicode=True) == "The Duke OF Veyl"
    assert normalize("  spaced\t out\n ", case_sensitive=False, normalize_unicode=True) == "spaced out"
    assert normalize("Ａ", case_sensitive=False, normalize_unicode=True) == "a"
    print("ok  normalizer: casefold, NFKC, whitespace collapse")


def verify_matcher() -> None:
    print()
    print("--- matcher ---")
    settings = BookSettings()
    entries = [
        Entry(id="veyl", keys=["Veyl"], content="x"),
        Entry(id="vel", keys=["vel"], content="x"),
        Entry(id="rx", key_regex=[r"\bthe (duke|duchess)\b"], content="x"),
    ]
    m = Matcher(entries, settings)
    ids = {h.entry_id for h in m.scan("the Duke of Veyl rides tonight")}
    assert "veyl" in ids and "rx" in ids, ids
    ids2 = {h.entry_id for h in m.scan("a revelatory evening")}
    assert "vel" not in ids2, ids2
    print("ok  matcher: AC+regex hit, whole_word suppresses substring")


def _one_entry_book(entries: list[Entry], settings: BookSettings | None = None) -> Lorebook:
    return Lorebook(entries={e.id: e for e in entries}, settings=settings or BookSettings())


def verify_activation() -> None:
    print()
    print("--- activation ---")
    book = _one_entry_book([Entry(id="veyl", keys=["Veyl"], content="veyl body")])
    assert [e.id for e in activate(book, "the Veyl summoned us", character_id="x").activated] == ["veyl"]

    book = _one_entry_book([Entry(id="veyl", keys=["Veyl"], secondary_keys=["House", "duke"],
                                  secondary_logic=Logic.AND_ANY, content="veyl body")])
    assert [e.id for e in activate(book, "the duke of Veyl", character_id="x").activated] == ["veyl"]
    assert activate(book, "a Veyl walks by", character_id="x").activated == []

    book = _one_entry_book([Entry(id="veyl", keys=["Veyl"], secondary_keys=["House", "duke"],
                                  secondary_logic=Logic.AND_ALL, content="veyl body")])
    assert [e.id for e in activate(book, "duke Veyl of the House", character_id="x").activated] == ["veyl"]
    assert activate(book, "duke Veyl rides", character_id="x").activated == []

    book = _one_entry_book([Entry(id="veyl", keys=["Veyl"], secondary_keys=["imposter"],
                                  secondary_logic=Logic.NOT, content="veyl body")])
    assert [e.id for e in activate(book, "the Veyl approaches", character_id="x").activated] == ["veyl"]
    assert activate(book, "the Veyl imposter", character_id="x").activated == []

    book = _one_entry_book([Entry(id="primer", constant=True, content="world is Thannos")])
    assert [e.id for e in activate(book, "unrelated banter", character_id="x").activated] == ["primer"]

    book = _one_entry_book([
        Entry(id="A", keys=["Veyl"], content="See also House Marren for context."),
        Entry(id="B", keys=["Marren"], content="Marren body"),
    ])
    assert {e.id for e in activate(book, "the Veyl", character_id="x").activated} == {"A", "B"}

    book = _one_entry_book([
        Entry(id="A", keys=["Veyl"], content="See also House Marren."),
        Entry(id="B", keys=["Marren"], not_triggerable_by_recursion=True, content="Marren body"),
    ])
    assert {e.id for e in activate(book, "the Veyl", character_id="x").activated} == {"A"}

    book = _one_entry_book([Entry(id="secret", keys=["pass"], visibility=["mira"], content="secret word")])
    assert activate(book, "the pass is open", character_id="thorin").activated == []
    assert [e.id for e in activate(book, "the pass is open", character_id="mira").activated] == ["secret"]

    big = "x" * 200
    book = _one_entry_book(
        [
            Entry(id="hi", keys=["word"], priority=10, content=big),
            Entry(id="lo", keys=["word"], priority=1, content=big),
        ],
        settings=BookSettings(token_budget=50),
    )
    for e in book.entries.values():
        e.token_count = (len(e.content) + 3) // 4
    r = activate(book, "the word fires both", character_id="x")
    assert [e.id for e in r.activated] == ["hi"], r.activated
    assert any(t.entry_id == "lo" and t.dropped_budget for t in r.trace), r.trace
    print("ok  activation covers direct/AND_ANY/AND_ALL/NOT/constant/recursion/visibility/budget")


def verify_repo_roundtrip() -> None:
    print()
    print("--- repo roundtrip ---")
    _cleanup_verify_rows()
    repo = LorebookRepository()
    entry = Entry(
        id=f"{VERIFY_PREFIX}veyl",
        title="House Veyl",
        keys=["Veyl"],
        key_regex=[r"\bveylish\b"],
        secondary_keys=["House", "duke"],
        secondary_logic=Logic.AND_ANY,
        constant=False,
        priority=10,
        position=Position.AFTER,
        no_recurse_into=False,
        not_triggerable_by_recursion=False,
        visibility=Visibility.GLOBAL,
        content="House Veyl rules the eastern march.",
    )
    repo.upsert(entry)
    try:
        read = repo.get(entry.id)
        assert read is not None
        assert read.id == entry.id
        assert read.keys == ["Veyl"]
        assert read.key_regex == [r"\bveylish\b"]
        assert read.secondary_logic == Logic.AND_ANY
        assert read.visibility == Visibility.GLOBAL
        assert read.token_count == (len(entry.content) + 3) // 4
        print(f"ok  upsert + get roundtrip; token_count={read.token_count}")

        # List summaries reflects the entry.
        ids = [s["id"] for s in repo.list_summaries()]
        assert entry.id in ids, ids
        print("ok  list_summaries contains the new id")

        # Partial update via upsert.
        updated = entry.model_copy(update={"title": "House Veyl (updated)", "priority": 20})
        repo.upsert(updated)
        read2 = repo.get(entry.id)
        assert read2.title == "House Veyl (updated)"
        assert read2.priority == 20
        print("ok  upsert overwrites fields on existing id")

        # List-style visibility roundtrip.
        list_entry = entry.model_copy(update={"id": f"{VERIFY_PREFIX}secret", "visibility": ["thorin"]})
        repo.upsert(list_entry)
        read_list = repo.get(list_entry.id)
        assert read_list.visibility == ["thorin"], read_list.visibility
        print("ok  list-shaped visibility roundtrips as a list")

        # Delete + double-delete.
        assert repo.delete(entry.id) is True
        assert repo.delete(entry.id) is False
        assert repo.get(entry.id) is None
        print("ok  delete returns True once, False thereafter")
    finally:
        _cleanup_verify_rows()


def verify_settings_roundtrip() -> None:
    print()
    print("--- settings roundtrip ---")
    repo = LorebookRepository()
    original = repo.get_settings()
    try:
        tweaked = original.model_copy(update={"token_budget": 123, "max_recursion": 7})
        repo.update_settings(tweaked)
        read = repo.get_settings()
        assert read.token_budget == 123 and read.max_recursion == 7
        print(f"ok  update_settings persists ({read.token_budget=}, {read.max_recursion=})")
    finally:
        repo.update_settings(original)


def verify_validation() -> None:
    print()
    print("--- validation ---")
    repo = LorebookRepository()

    # Empty content.
    try:
        repo.upsert(Entry(id=f"{VERIFY_PREFIX}empty", content="   "))
    except ValueError as e:
        assert "empty" in str(e).lower()
        print("ok  empty content -> ValueError")
    else:
        raise AssertionError("expected ValueError for empty content")

    # Visibility against unknown character id -> validate_visibility returns an error.
    entry = Entry(id=f"{VERIFY_PREFIX}secret", content="body", visibility=["__ghost_not_in_db__"])
    errors = validate_visibility(entry)
    assert errors and "unknown character" in errors[0], errors
    print("ok  validate_visibility flags unknown cids")


def verify_api_crud() -> None:
    print()
    print("--- API CRUD ---")
    from api.app import app

    with TestClient(app) as c:
        _cleanup_verify_rows()
        entry_id = f"{VERIFY_PREFIX}veyl"
        try:
            payload = {
                "id": entry_id,
                "title": "Verify Veyl",
                "keys": ["Veyl"],
                "key_regex": [],
                "secondary_keys": [],
                "secondary_logic": "and_any",
                "constant": False,
                "priority": 5,
                "position": "after",
                "no_recurse_into": False,
                "not_triggerable_by_recursion": False,
                "visibility": "global",
                "content": "House Veyl rules the eastern march.",
            }
            r = c.post("/api/lorebook/entries", json=payload)
            assert r.status_code == 201, r.text
            print("ok  POST /api/lorebook/entries -> 201")

            r = c.post("/api/lorebook/entries", json=payload)
            assert r.status_code == 409, r.text
            print("ok  POST duplicate id -> 409")

            summaries = c.get("/api/lorebook/entries").json()["items"]
            assert any(s["id"] == entry_id for s in summaries), summaries
            print("ok  GET /api/lorebook/entries lists the new entry")

            # In-memory refresh after write.
            assert entry_id in app.state.lorebook.entries, list(app.state.lorebook.entries)
            print("ok  app.state.lorebook refreshed after POST (no reload call)")

            updated = {**payload, "title": "Verify Veyl v2"}
            r = c.put(f"/api/lorebook/entries/{entry_id}", json=updated)
            assert r.status_code == 200, r.text
            assert c.get(f"/api/lorebook/entries/{entry_id}").json()["title"] == "Verify Veyl v2"
            print("ok  PUT updates")

            r = c.put(f"/api/lorebook/entries/{entry_id}", json={**payload, "id": "mismatch"})
            assert r.status_code == 400, r.text
            print("ok  PUT with mismatched id -> 400")

            # Reload endpoint is gone.
            r = c.post("/api/lorebook/reload")
            assert r.status_code == 404, r.text
            print("ok  POST /api/lorebook/reload is removed (404)")

            r = c.delete(f"/api/lorebook/entries/{entry_id}")
            assert r.status_code == 204, r.text
            r = c.delete(f"/api/lorebook/entries/{entry_id}")
            assert r.status_code == 404, r.text
            print("ok  DELETE idempotent -> 204 then 404")

            # In-memory refresh after delete.
            assert entry_id not in app.state.lorebook.entries
            print("ok  app.state.lorebook refreshed after DELETE")
        finally:
            _cleanup_verify_rows()


def verify_html_pages() -> None:
    print()
    print("--- HTML pages ---")
    from api.app import app

    with TestClient(app) as c:
        r = c.get("/lorebook")
        assert r.status_code == 200
        assert "<h1>Lorebook</h1>" in r.text
        print("ok  GET /lorebook renders list page")

        r = c.get("/lorebook/new")
        assert r.status_code == 200
        for frag in ['x-data="lorebookForm(', 'id="roster"'.replace('id="roster"', 'secondary_logic'), 'visibility']:
            assert frag in r.text, frag
        print("ok  GET /lorebook/new renders the form")

        r = c.get("/lorebook/__does_not_exist__/edit")
        assert r.status_code == 404
        print("ok  GET /lorebook/{missing}/edit -> 404")


def main() -> int:
    verify_normalizer()
    verify_matcher()
    verify_activation()
    verify_repo_roundtrip()
    verify_settings_roundtrip()
    verify_validation()
    verify_api_crud()
    verify_html_pages()
    print()
    print("all lorebook verifications passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
