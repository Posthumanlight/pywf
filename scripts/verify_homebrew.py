"""Non-model verification of the two-file catalog (core + homebrew)."""
import importlib
import shutil
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HOMEBREW = Path(__file__).resolve().parents[1] / "data" / "rules" / "homebrew.md"

SAMPLE = """\
# Classes

## Blood Hunter

### Blood Hunter Class Features

#### Level 1: Blood Mark

The Blood Hunter marks a target with blood magic.

### Blood Hunter Subclass: Order of the Lycan

## Fighter

### Fighter Subclass: Blade Master

#### Level 3: Precision Edge

The Blade Master gains a precision edge on weapon rolls.

# Character Origins

## Character Species

### Species Descriptions

#### Shardkin

_**Crystal Skin.**_ You have resistance to bludgeoning damage.

# Feats

## Feat Descriptions

#### Lucky Streak

# Spells

## Spell Descriptions

### Superfireball

_Level 4 Evocation (Wizard)_
"""

CONFLICTING = """\
# Spells

## Spell Descriptions

### Fireball

_Level 3 Evocation (Wizard)_
"""


def _reload_catalog():
    import data.srd_catalog as mod
    importlib.reload(mod)
    return mod


def _restore(backup: bytes | None):
    if backup is None:
        if HOMEBREW.exists():
            HOMEBREW.unlink()
    else:
        HOMEBREW.write_bytes(backup)


def main() -> int:
    backup = HOMEBREW.read_bytes() if HOMEBREW.exists() else None

    try:
        print("--- baseline (empty homebrew) ---")
        HOMEBREW.write_text("", encoding="utf-8")
        mod = _reload_catalog()
        assert len(mod.CLASSES) == 12 and len(mod.SPECIES) == 9 and len(mod.FEATS) == 17
        assert len(mod.SPELLS) == 339 and sum(len(v) for v in mod.SUBCLASSES.values()) == 12
        assert "Fighter" in mod.CLASSES and "(Homebrew)" not in " ".join(mod.CLASSES)
        print("ok  SRD-only counts preserved (12/9/17/12/339)")

        print()
        print("--- sample homebrew merge ---")
        HOMEBREW.write_text(SAMPLE, encoding="utf-8")
        mod = _reload_catalog()
        assert "Blood Hunter (Homebrew)" in mod.CLASSES
        assert "Shardkin (Homebrew)" in mod.SPECIES
        assert "Lucky Streak (Homebrew)" in mod.FEATS
        assert "Blade Master (Homebrew)" in mod.SUBCLASSES["Fighter"]
        assert "Champion" in mod.SUBCLASSES["Fighter"]
        assert mod.SUBCLASSES["Blood Hunter (Homebrew)"] == ["Order of the Lycan (Homebrew)"]
        superfire = [s for s in mod.SPELLS if s["name"] == "Superfireball (Homebrew)"]
        assert superfire and superfire[0]["level"] == 4 and superfire[0]["school"] == "Evocation"
        # Classes/species alphabetical
        assert mod.CLASSES == sorted(mod.CLASSES)
        assert mod.SPECIES == sorted(mod.SPECIES)
        print("ok  homebrew entries merged with ' (Homebrew)' suffix")
        print(f"    classes now {len(mod.CLASSES)}, species {len(mod.SPECIES)}, feats {len(mod.FEATS)}, spells {len(mod.SPELLS)}")

        print()
        print("--- homebrew progressions merged ---")
        bh_feats = mod.CLASS_FEATURES.get("Blood Hunter (Homebrew)") or {}
        assert "Blood Mark" in bh_feats.get(1, []), bh_feats
        print("ok  homebrew class features surfaced under suffixed key")

        bm_feats = mod.SUBCLASS_FEATURES.get("Fighter: Blade Master (Homebrew)") or {}
        assert "Precision Edge" in bm_feats.get(3, []), bm_feats
        print("ok  homebrew subclass features surfaced under '<Parent>: <Sub (Homebrew)>' key")

        shardkin_feats = mod.SPECIES_FEATURES.get("Shardkin (Homebrew)") or []
        assert "Crystal Skin" in shardkin_feats, shardkin_feats
        print("ok  homebrew species features surfaced under suffixed key")

        print()
        print("--- form page picks up the homebrew entries ---")
        # Re-import api.app so routes see the fresh catalog
        import api.pages
        importlib.reload(api.pages)
        import api.characters
        importlib.reload(api.characters)
        import api.app
        importlib.reload(api.app)
        from fastapi.testclient import TestClient
        with TestClient(api.app.app) as c:
            body = c.get("/characters/new").text
        assert 'value="Blood Hunter (Homebrew)"' in body
        assert 'value="Blade Master (Homebrew)"' in body
        assert 'id="srd-subclass-Fighter"' in body
        assert '"Superfireball (Homebrew)"' in body
        print("ok  datalists + spell JSON include homebrew entries")

        print()
        print("--- collision detection ---")
        HOMEBREW.write_text(CONFLICTING, encoding="utf-8")
        try:
            _reload_catalog()
            print("FAIL: expected ValueError on duplicate Fireball")
            return 1
        except ValueError as exc:
            assert "Fireball" in str(exc)
            print(f"ok  ValueError raised: {str(exc).splitlines()[0]}")
            print(f"    {str(exc).splitlines()[-1]}")

        print()
        print("all homebrew verifications passed")
        return 0
    except AssertionError:
        traceback.print_exc()
        return 1
    finally:
        _restore(backup)
        # Reload once more so the final state matches the on-disk file.
        try:
            _reload_catalog()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
