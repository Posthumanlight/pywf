"""Non-model verification of the character CRUD API + HTML pages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api.app import app

TEST_ID = "pytest_rook"

BODY = {
    "id": TEST_ID,
    "name": "Rook",
    "species": "Human",
    "abilities": {"str": 10, "dex": 14, "con": 12, "int": 11, "wis": 10, "cha": 15},
    "classes": [{"class": "Rogue", "level": 1, "subclass": None}],
    "equipment": [{"name": "Rapier", "qty": 1}, {"name": "Daggers", "qty": 2}],
    "languages": ["Common", "Thieves' Cant"],
}


def main() -> int:
    with TestClient(app) as c:
        # Clean up any leftover from a prior failed run.
        c.delete(f"/api/characters/{TEST_ID}")

        # --- JSON API ---
        print("--- JSON CRUD ---")
        r = c.post("/api/characters", json=BODY)
        assert r.status_code == 201, r.status_code
        assert r.json() == {"id": TEST_ID, "name": "Rook"}
        print("ok  POST /api/characters -> 201", r.json())

        r = c.get("/api/characters")
        ids = [x["id"] for x in r.json()["items"]]
        assert TEST_ID in ids
        print("ok  GET /api/characters includes new id")

        r = c.get(f"/api/characters/{TEST_ID}")
        assert r.status_code == 200
        sheet = r.json()
        assert sheet["name"] == "Rook"
        assert sheet["classes"] == [{"class": "Rogue", "level": 1, "subclass": None}]
        assert sheet["equipment"] == [{"name": "Rapier", "qty": 1}, {"name": "Daggers", "qty": 2}]
        print("ok  GET /api/characters/{id} returns parsed sheet")

        r = c.post("/api/characters", json=BODY)
        assert r.status_code == 409
        assert r.json()["detail"]["id"] == TEST_ID
        print("ok  POST same id -> 409 Conflict")

        updated = {**BODY, "name": "Rook the Clever"}
        r = c.put(f"/api/characters/{TEST_ID}", json=updated)
        assert r.status_code == 200
        print("ok  PUT /api/characters/{id} -> 200", r.json())
        assert c.get(f"/api/characters/{TEST_ID}").json()["name"] == "Rook the Clever"

        r = c.put(f"/api/characters/{TEST_ID}", json={**updated, "id": "wrong"})
        assert r.status_code == 400
        print("ok  PUT with mismatched id -> 400")

        r = c.put("/api/characters/does_not_exist", json={**BODY, "id": "does_not_exist"})
        assert r.status_code == 404
        print("ok  PUT on missing id -> 404")

        r = c.post("/api/characters", json={"id": "x", "not_a_field": 1})
        assert r.status_code == 422
        print("ok  POST unknown field -> 422")

        r = c.delete(f"/api/characters/{TEST_ID}")
        assert r.status_code == 204
        print("ok  DELETE -> 204")
        r = c.delete(f"/api/characters/{TEST_ID}")
        assert r.status_code == 404
        print("ok  DELETE again -> 404")

        # --- HTML pages ---
        print()
        print("--- HTML pages ---")
        r = c.get("/characters")
        assert r.status_code == 200
        assert "<title>pywf</title>" in r.text
        assert "alpinejs" in r.text
        assert "htmx.org" in r.text
        print(f"ok  GET /characters -> 200 HTML ({len(r.text)} bytes)")

        r = c.get("/characters/new")
        assert r.status_code == 200
        assert 'x-data="characterForm(' in r.text
        print(f"ok  GET /characters/new -> 200 HTML ({len(r.text)} bytes)")

        # Seed a sheet, read the edit page, verify the initial state is embedded.
        c.post("/api/characters", json=BODY)
        try:
            r = c.get(f"/characters/{TEST_ID}/edit")
            assert r.status_code == 200
            # Fields are HTML-escaped inside the x-data attribute now.
            assert "&quot;name&quot;: &quot;Rook&quot;" in r.text, "edit page should embed sheet name (escaped)"
            assert "&quot;id&quot;: &quot;pytest_rook&quot;" in r.text
            print(f"ok  GET /characters/{{id}}/edit -> 200 HTML prefilled")
        finally:
            c.delete(f"/api/characters/{TEST_ID}")

        r = c.get("/characters/does_not_exist/edit")
        assert r.status_code == 404
        print("ok  GET /characters/{missing}/edit -> 404")

        # --- form attribute escaping ---
        print()
        print("--- form escaping ---")
        body = c.get("/characters/new").text
        x_data = body.split('x-data="', 1)[1].split('"', 1)[0]
        assert "characterForm(" in x_data, "x-data must contain the component invocation"
        assert "&quot;" in x_data, "JSON strings inside x-data must be HTML-escaped"
        assert '"' not in x_data[len("characterForm("):], (
            "no raw double quotes allowed inside the x-data attribute value"
        )
        print(f"ok  x-data attribute is HTML-escaped ({len(x_data)} chars)")

        # The dict-field block is inside a <template x-for>, so the source HTML has
        # exactly one nested x-data definition that Alpine clones per iteration.
        count = body.count('x-data="{ newKey:')
        assert count == 1, f"expected 1 nested dict-field x-data definition, got {count}"
        print(f"ok  nested x-data scope defined for dict fields (Alpine clones per iteration)")

        assert "[x-cloak] { display: none; }" in body, "missing x-cloak CSS rule"
        print("ok  x-cloak CSS rule present")

        # --- SRD dropdowns ---
        print()
        print("--- SRD dropdowns ---")
        assert 'id="srd-classes"' in body and 'value="Wizard"' in body
        assert 'id="srd-species"' in body and 'value="Dragonborn"' in body
        assert 'id="srd-feats"' in body and 'value="Alert"' in body
        assert 'id="srd-subclass-Fighter"' in body and 'value="Champion"' in body
        print("ok  datalists embedded (classes/species/feats/subclass-Fighter)")

        assert "window.SRD_SPELLS" in body
        assert '"Acid Arrow"' in body and '"Acid Splash"' in body
        print("ok  window.SRD_SPELLS payload embedded")

        assert 'list="srd-species"' in body
        assert 'list="srd-classes"' in body
        assert 'list="srd-feats"' in body
        assert ":list=\"'srd-subclass-' + (c.class || '')\"" in body
        print("ok  inputs reference the datalists (incl. dynamic subclass binding)")

        assert 'x-data="spellPicker(s' in body  # loose match: new signature takes a callback
        assert 'x-model.number="levelFilter"' in body
        assert "window.spellPicker" in body
        print("ok  spell picker widget + Alpine helper present")

    print()
    print("all character-API verifications passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
