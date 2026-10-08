"""Non-model verification of the SRD-rules panel: catalog bodies, endpoint, form bindings."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api.app import app
from data.srd_catalog import BODIES, CLASS_CANTRIPS, CLASS_FEATURES, SPECIES_FEATURES, SUBCLASS_FEATURES, get_body


def main() -> int:
    print("--- catalog bodies ---")
    for key in (("spell", "Acid Arrow"), ("class", "Fighter"), ("feat", "Alert"),
                ("species", "Dwarf"), ("subclass", "Champion")):
        assert key in BODIES, f"missing {key} in BODIES"
    print(f"ok  BODIES populated ({len(BODIES)} entries)")

    fireball = get_body("spell", "Fireball")
    assert fireball and len(fireball) > 100
    print(f"ok  get_body('spell','Fireball') -> {len(fireball)} chars")

    fighter = get_body("class", "Fighter")
    assert fighter and len(fighter) > 1000  # class bodies are long
    print(f"ok  get_body('class','Fighter') -> {len(fighter)} chars (scrollable)")

    assert get_body("spell", "__missing__") is None
    print("ok  missing name -> None")

    print()
    print("--- SRD endpoint ---")
    with TestClient(app) as c:
        r = c.get("/api/srd/spell/Fireball")
        assert r.status_code == 200, r.status_code
        data = r.json()
        assert data["category"] == "spell" and data["name"] == "Fireball"
        assert "Fire" in data["body"] and len(data["body"]) > 100
        print(f"ok  GET /api/srd/spell/Fireball -> 200 ({len(data['body'])} bytes)")

        r = c.get("/api/srd/class/Fighter")
        assert r.status_code == 200
        assert len(r.json()["body"]) > 1000
        print(f"ok  GET /api/srd/class/Fighter -> 200 ({len(r.json()['body'])} bytes)")

        r = c.get("/api/srd/spell/__missing__")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error"] == "not found" and detail["name"] == "__missing__"
        print("ok  GET /api/srd/spell/__missing__ -> 404")

        r = c.get("/api/srd/junk/Fireball")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "unknown category"
        print("ok  GET /api/srd/junk/Fireball -> 400")

        print()
        print("--- form page bindings ---")
        body = c.get("/characters/new").text
        for frag in [
            'class="form-page"',
            'class="form-grid"',
            'class="srd-column"',
            'class="srd-fab"',
            'class="srd-overlay"',
            'x-text="srd.name',
            'x-html="srd.html"',
            "showSrd('species', form.species)",
            "showSrd('class', c.class)",
            "showSrd('subclass', c.subclass)",
            "showSrd('feat', f.name)",
            "showSrd('spell', s.name)",
            "spellPicker(s, (name) => showSrd('spell', name))",
            "async showSrd(category, name)",
            "marked.parse",
            "cdn.jsdelivr.net/npm/marked",
            "max-width: 900px",
            "srdOpen",
            "clamp(300px, 32vw, 520px)",
            "body:has(.form-page)",
            "max-width: 1600px",
        ]:
            assert frag in body, f"missing in form page: {frag!r}"
        # Old inline SRD fieldset must be gone — the panel moved to the right column.
        assert "<legend>SRD rules</legend>" not in body
        # Panel is adaptive now; the old fixed 360px grid column must be gone.
        assert "minmax(0, 1fr) 360px" not in body
        # Old 1240px form-page cap must be gone.
        assert "max-width: 1240px" not in body
        print("ok  sticky panel + markdown + fluid clamp + wider form-page cap all present")

        print()
        print("--- progressions catalog ---")
        fighter = CLASS_FEATURES.get("Fighter") or {}
        assert "Fighting Style" in fighter.get(1, []) and "Second Wind" in fighter.get(1, []) and "Weapon Mastery" in fighter.get(1, [])
        assert "Action Surge" in fighter.get(2, []) and "Tactical Mind" in fighter.get(2, [])
        assert any("Subclass" in n or "Martial Archetype" in n for n in fighter.get(3, []))
        print(f"ok  Fighter class features (levels 1-3) extracted")

        elf = SPECIES_FEATURES.get("Elf") or []
        assert set(elf) >= {"Darkvision", "Elven Lineage", "Fey Ancestry", "Keen Senses", "Trance"}, elf
        print(f"ok  Elf species features extracted ({len(elf)})")

        champ = SUBCLASS_FEATURES.get("Fighter: Champion") or {}
        assert 3 in champ and champ[3], champ
        print(f"ok  Fighter: Champion subclass features extracted (level 3: {champ[3]})")

        wiz_cantrips = CLASS_CANTRIPS.get("Wizard") or []
        assert "Fire Bolt" in wiz_cantrips, wiz_cantrips[:5]
        assert not CLASS_CANTRIPS.get("Fighter"), CLASS_CANTRIPS.get("Fighter")
        print(f"ok  CLASS_CANTRIPS populated for casters, empty for Fighter")

        print()
        print("--- form page progressions wiring ---")
        for frag in [
            "window.SRD_PROGRESSIONS",
            "addClassFeatures",
            "addSpeciesFeatures",
            "addClassCantrips",
            "onSpeciesChange",
            "onClassChange",
        ]:
            assert frag in body, f"missing in form page: {frag!r}"
        print("ok  SRD_PROGRESSIONS + Alpine helpers wired into the form")

        print()
        print("--- '+ features' button placement ---")
        for frag in [
            'class="row-with-action"',
            'class="action-side"',
            ".row-with-action { display: grid",
        ]:
            assert frag in body, f"missing in form page: {frag!r}"
        # Species "+ features" button is bound in exactly one spot (the lifted-out row).
        assert body.count('@click="addSpeciesFeatures()"') == 1
        print("ok  '+ features' buttons use row-with-action + action-side slot")

        print()
        print("--- edit page passes initial data without breaking ---")
        # Seed Thorin via the existing fixture; must round-trip through POST.
        rook_body = {
            "id": "pytest_srd_rook", "name": "Rook",
            "species": "Elf",  # SRD species to exercise initial-state binding
            "abilities": {"str": 10, "dex": 14, "con": 12, "int": 11, "wis": 10, "cha": 15},
        }
        c.delete(f"/api/characters/{rook_body['id']}")
        c.post("/api/characters", json=rook_body)
        try:
            r = c.get(f"/characters/{rook_body['id']}/edit")
            assert r.status_code == 200
            assert 'class="srd-column"' in r.text
        finally:
            c.delete(f"/api/characters/{rook_body['id']}")
        print("ok  /characters/{id}/edit still renders with the panel")

    print()
    print("all SRD-panel verifications passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
