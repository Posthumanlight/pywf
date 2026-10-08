"""Non-model verification of the lorebook: loader, matcher, activation, API."""
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from lorebook.activation import activate
from lorebook.loader import LorebookValidationError, load
from lorebook.matcher import Matcher
from lorebook.models import BookSettings, Entry, Logic, Position, Visibility
from lorebook.normalizer import normalize


def _write(dir_path: Path, name: str, body: str) -> Path:
    p = dir_path / name
    p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return p


def verify_normalizer() -> None:
    print("--- normalizer ---")
    assert normalize("The Duke OF Veyl", case_sensitive=False, normalize_unicode=True) == "the duke of veyl"
    assert normalize("The Duke OF Veyl", case_sensitive=True, normalize_unicode=True) == "The Duke OF Veyl"
    assert normalize("  spaced\t out\n ", case_sensitive=False, normalize_unicode=True) == "spaced out"
    # NFKC: fullwidth 'A' -> ascii 'a' after casefold
    assert normalize("Ａ", case_sensitive=False, normalize_unicode=True) == "a"
    print("ok  normalizer: casefold, NFKC, whitespace collapse")


def verify_matcher() -> None:
    print()
    print("--- matcher ---")
    settings = BookSettings()  # case_sensitive=False, whole_word=True
    entries = [
        Entry(id="veyl", keys=["Veyl"], content="x"),
        Entry(id="vel", keys=["vel"], content="x"),
        Entry(id="rx", key_regex=[r"\bthe (duke|duchess)\b"], content="x"),
    ]
    m = Matcher(entries, settings)

    ids = {h.entry_id for h in m.scan("the Duke of Veyl rides tonight")}
    assert "veyl" in ids, ids
    assert "rx" in ids, ids
    # whole_word: 'vel' must NOT match inside 'revelatory'
    ids2 = {h.entry_id for h in m.scan("a revelatory evening")}
    assert "vel" not in ids2, ids2
    print("ok  matcher: AC+regex hit, whole_word suppresses substring")


def verify_loader_happy_path() -> None:
    print()
    print("--- loader (happy path) ---")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root, "_book.yaml", """
            scan_depth: 2
            token_budget: 500
            whole_word: true
        """)
        _write(root, "veyl.md", """
            ---
            id: veyl
            keys: ["Veyl"]
            priority: 10
            ---
            House Veyl rules the eastern march.
        """)
        _write(root, "primer.md", """
            ---
            id: primer
            constant: true
            ---
            The known world is called Thannos.
        """)
        _write(root, "yaml_entry.yaml", """
            id: raw
            keys: ["Marren"]
            content: |
              House Marren guards the north pass.
        """)
        _write(root, "README.md", "ignored\n")

        book = load(root)
        assert set(book.entries) == {"veyl", "primer", "raw"}, book.entries
        assert book.settings.token_budget == 500
        assert book.entries["primer"].constant is True
        # token_count = ceil(len/4)
        for e in book.entries.values():
            assert e.token_count == (len(e.content) + 3) // 4, (e.id, e.token_count, len(e.content))
    print("ok  loader parses md + yaml, skips README, honors _book.yaml, precomputes token_count")


def verify_loader_errors() -> None:
    print()
    print("--- loader (errors) ---")
    # Duplicate id
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root, "a.md", "---\nid: dup\nkeys: [\"a\"]\n---\nA body\n")
        _write(root, "b.md", "---\nid: dup\nkeys: [\"b\"]\n---\nB body\n")
        try:
            load(root)
        except LorebookValidationError as exc:
            assert any("duplicate" in e for e in exc.errors), exc.errors
            print("ok  duplicate id -> LorebookValidationError")
        else:
            raise AssertionError("expected LorebookValidationError")

    # Empty content
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root, "empty.md", "---\nid: empty\n---\n   \n")
        try:
            load(root)
        except LorebookValidationError as exc:
            assert any("empty content" in e for e in exc.errors), exc.errors
            print("ok  empty content -> LorebookValidationError")
        else:
            raise AssertionError("expected LorebookValidationError")

    # Visibility pointing at unknown character id
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root, "secret.md", """
            ---
            id: secret
            keys: ["secret"]
            visibility: ["__ghost_not_in_db__"]
            ---
            top secret
        """)
        try:
            load(root)
        except LorebookValidationError as exc:
            assert any("unknown character" in e for e in exc.errors), exc.errors
            print("ok  unknown character in visibility -> LorebookValidationError")
        else:
            raise AssertionError("expected LorebookValidationError")


def _one_entry_book(entries: list[Entry], settings: BookSettings | None = None):
    """Build a Lorebook in-memory (no filesystem) for activation tests."""
    from lorebook.loader import Lorebook
    s = settings or BookSettings()
    return Lorebook(path=Path("/dev/null"), entries={e.id: e for e in entries}, settings=s)


def verify_activation() -> None:
    print()
    print("--- activation ---")
    # Direct hit, with no secondaries.
    book = _one_entry_book([Entry(id="veyl", keys=["Veyl"], content="veyl body")])
    r = activate(book, "the Veyl summoned us", character_id="thorin")
    assert [e.id for e in r.activated] == ["veyl"], r.activated
    print("ok  direct keyword hit fires")

    # Secondary AND_ANY: fires with one secondary.
    book = _one_entry_book([Entry(id="veyl", keys=["Veyl"],
                                  secondary_keys=["House", "duke"],
                                  secondary_logic=Logic.AND_ANY, content="veyl body")])
    assert [e.id for e in activate(book, "the duke of Veyl", character_id="cid").activated] == ["veyl"]
    # AND_ANY with neither secondary present → suppressed.
    assert [e.id for e in activate(book, "a Veyl walks by", character_id="cid").activated] == []
    print("ok  AND_ANY secondary gate works both ways")

    # AND_ALL
    book = _one_entry_book([Entry(id="veyl", keys=["Veyl"],
                                  secondary_keys=["House", "duke"],
                                  secondary_logic=Logic.AND_ALL, content="veyl body")])
    assert [e.id for e in activate(book, "duke Veyl of the House", character_id="cid").activated] == ["veyl"]
    assert [e.id for e in activate(book, "duke Veyl rides", character_id="cid").activated] == []
    print("ok  AND_ALL secondary gate works both ways")

    # NOT
    book = _one_entry_book([Entry(id="veyl", keys=["Veyl"],
                                  secondary_keys=["imposter"],
                                  secondary_logic=Logic.NOT, content="veyl body")])
    assert [e.id for e in activate(book, "the Veyl approaches", character_id="cid").activated] == ["veyl"]
    assert [e.id for e in activate(book, "the Veyl imposter", character_id="cid").activated] == []
    print("ok  NOT secondary gate works both ways")

    # Constant
    book = _one_entry_book([Entry(id="primer", constant=True, content="world is Thannos")])
    assert [e.id for e in activate(book, "unrelated banter", character_id="cid").activated] == ["primer"]
    print("ok  constant entry fires without keys")

    # Recursion: A activates, A's content mentions B's key, B fires.
    book = _one_entry_book([
        Entry(id="A", keys=["Veyl"], content="See also House Marren for context."),
        Entry(id="B", keys=["Marren"], content="Marren body"),
    ])
    r = activate(book, "the Veyl", character_id="cid")
    assert {e.id for e in r.activated} == {"A", "B"}, r.activated
    # not_triggerable_by_recursion blocks B.
    book = _one_entry_book([
        Entry(id="A", keys=["Veyl"], content="See also House Marren."),
        Entry(id="B", keys=["Marren"], not_triggerable_by_recursion=True, content="Marren body"),
    ])
    r = activate(book, "the Veyl", character_id="cid")
    assert {e.id for e in r.activated} == {"A"}, r.activated
    print("ok  recursion fires linked entries; not_triggerable_by_recursion blocks it")

    # Visibility list filters per-agent.
    book = _one_entry_book([Entry(id="secret", keys=["pass"], visibility=["mira"], content="secret word")])
    assert [e.id for e in activate(book, "the pass is open", character_id="thorin").activated] == []
    assert [e.id for e in activate(book, "the pass is open", character_id="mira").activated] == ["secret"]
    print("ok  visibility list filters per character")

    # Budget drops lowest priority first.
    big = "x" * 200  # token_count = 50
    book = _one_entry_book(
        [
            Entry(id="hi", keys=["word"], priority=10, content=big),
            Entry(id="lo", keys=["word"], priority=1, content=big),
        ],
        settings=BookSettings(token_budget=50),
    )
    # Precompute token_count the way loader would:
    for e in book.entries.values():
        e.token_count = (len(e.content) + 3) // 4
    r = activate(book, "the word fires both", character_id="cid")
    assert [e.id for e in r.activated] == ["hi"], r.activated
    assert any(t.entry_id == "lo" and t.dropped_budget for t in r.trace), r.trace
    print("ok  budget drops lower-priority entries and traces them")


def verify_api() -> None:
    print()
    print("--- API endpoints ---")
    # Importing app triggers lifespan on TestClient enter -- lifespan reads data/lore/
    # which contains the shipped example entry.
    from api.app import app

    with TestClient(app) as c:
        r = c.get("/api/lorebook")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "settings" in data and "entries" in data
        ids = {e["id"] for e in data["entries"]}
        print(f"ok  GET /api/lorebook lists {len(data['entries'])} entries ({sorted(ids)}) from {data['path']}")

        r = c.post("/api/lorebook/reload")
        assert r.status_code == 200, r.text
        assert r.json()["entries"] == len(data["entries"])
        print("ok  POST /api/lorebook/reload re-reads the directory")

        # Validation failure path: write a bad file into the real dir (duplicates one of
        # the existing entry ids), reload, assert 400, confirm the previous in-memory book
        # is unchanged, then clean up.
        from settings.settings import settings as _settings
        bad = _settings.BASE_PATH / "data" / "lore" / "__verify_bad.md"
        duplicate_id = next(iter(ids)) if ids else "ghost"
        bad.write_text(
            f"---\nid: {duplicate_id}\n---\nduplicate id with an existing entry\n",
            encoding="utf-8",
        )
        try:
            r = c.post("/api/lorebook/reload")
            if ids:
                assert r.status_code == 400, r.text
                detail = r.json()["detail"]
                assert detail["error"] == "invalid lorebook"
                assert any("duplicate" in e for e in detail["errors"]), detail
                still = c.get("/api/lorebook").json()
                assert {e["id"] for e in still["entries"]} == ids
                print("ok  invalid reload returns 400 and leaves the previous book intact")
            else:
                # No entries to duplicate against; reload should just succeed with 1 entry.
                assert r.status_code == 200
                print("ok  reload with no prior entries loaded the new file (no duplicate possible)")
        finally:
            if bad.exists():
                bad.unlink()


def main() -> int:
    verify_normalizer()
    verify_matcher()
    verify_loader_happy_path()
    verify_loader_errors()
    verify_activation()
    verify_api()
    print()
    print("all lorebook verifications passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
