"""Enumerate 5.5e SRD content for UI dropdowns.

Parses `data/rules/core_rules.md` and (optionally) `data/rules/homebrew.md`
once at import. Homebrew entries are suffixed with ' (Homebrew)' in their
visible names so they're distinguishable in dropdowns and stored sheets.
Collisions between homebrew and SRD raise `ValueError` at import time.
"""
import re
from pathlib import Path

from settings.settings import settings

_CORE_PATH = settings.BASE_PATH / "data" / "rules" / "core_rules.md"
_HOMEBREW_PATH = settings.BASE_PATH / "data" / "rules" / "homebrew.md"
_HOMEBREW_SUFFIX = " (Homebrew)"

_SPELL_META_RE = re.compile(
    r"^_(?:Level (?P<level>\d+) )?(?P<school>[A-Za-z]+)(?P<cantrip> Cantrip)?(?: \((?P<classes>[^)]+)\))?_\s*$"
)
_SUBCLASS_RE = re.compile(r"^### (?P<class>\S[^:]*?) Subclass:\s+(?P<name>.+?)\s*$")


def _parse_file(path: Path) -> dict:
    """Parse one SRD-formatted markdown file. Returns a dict with keys
    'classes', 'species', 'feats', 'subclasses', 'spells'. Returns empty
    collections if the file does not exist or is empty.
    """
    empty: dict = {"classes": [], "species": [], "feats": [], "subclasses": {}, "spells": []}
    if not path.exists():
        return empty

    classes: list[str] = []
    species: list[str] = []
    feats: list[str] = []
    subclasses: dict[str, list[str]] = {}
    spells: list[dict] = []

    h1 = h2 = h3 = ""
    current_class = ""
    pending_spell: str | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()

        if line.startswith("# "):
            h1 = line[2:].strip()
            h2 = h3 = ""
            current_class = ""
            pending_spell = None
            continue

        if line.startswith("## "):
            h2 = line[3:].strip()
            h3 = ""
            if h1 == "Classes":
                if h2 not in classes:
                    classes.append(h2)
                current_class = h2
            else:
                current_class = ""
            continue

        if line.startswith("### "):
            h3 = line[4:].strip()
            m = _SUBCLASS_RE.match(line)
            if m and h1 == "Classes" and current_class:
                subclasses.setdefault(current_class, []).append(m.group("name").strip())
                continue
            if h2 == "Spell Descriptions":
                pending_spell = h3
            continue

        if line.startswith("#### "):
            name = line[5:].strip()
            if h2 == "Character Species" and h3 == "Species Descriptions":
                species.append(name)
            elif h2 == "Feat Descriptions":
                feats.append(name)
            continue

        if pending_spell and line.strip():
            m = _SPELL_META_RE.match(line.strip())
            if m:
                level = int(m.group("level")) if m.group("level") else 0
                school = m.group("school")
                classes_raw = m.group("classes") or ""
                caster_classes = [c.strip() for c in classes_raw.split(",") if c.strip()]
                spells.append(
                    {
                        "name": pending_spell,
                        "level": level,
                        "school": school,
                        "classes": caster_classes,
                    }
                )
                pending_spell = None

    return {
        "classes": classes,
        "species": species,
        "feats": feats,
        "subclasses": subclasses,
        "spells": spells,
    }


def _merge(core: dict, hb: dict) -> dict:
    """Combine SRD + homebrew. Raises ValueError on leaf-name collisions.

    `## <Class>` headings in homebrew that already exist in SRD are treated as
    *parent context* (so the author can declare `## Fighter` only to attach a
    new subclass to SRD Fighter), not as new classes — no collision there.
    Collisions are reported for subclasses, species, feats, and spells.
    """
    # Only classes that are truly new in homebrew get added (with suffix).
    core_class_set = set(core["classes"])
    truly_new_hb_classes = [c for c in hb["classes"] if c not in core_class_set]
    hb_new_class_set = set(truly_new_hb_classes)

    conflicts: list[str] = []
    for cat in ("species", "feats"):
        overlap = set(core[cat]) & set(hb[cat])
        conflicts.extend(f"{cat}: {name!r}" for name in sorted(overlap))
    for cls, names in hb["subclasses"].items():
        core_names = set(core["subclasses"].get(cls, []))
        overlap = core_names & set(names)
        conflicts.extend(f"subclass of {cls!r}: {name!r}" for name in sorted(overlap))
    core_spell_names = {s["name"] for s in core["spells"]}
    hb_spell_names = {s["name"] for s in hb["spells"]}
    conflicts.extend(f"spells: {name!r}" for name in sorted(core_spell_names & hb_spell_names))
    if conflicts:
        raise ValueError(
            "homebrew.md redefines SRD entries:\n  - " + "\n  - ".join(conflicts)
        )

    sfx = _HOMEBREW_SUFFIX
    merged_classes = sorted(set(core["classes"] + [c + sfx for c in truly_new_hb_classes]))
    merged_species = sorted(set(core["species"] + [s + sfx for s in hb["species"]]))
    merged_feats = sorted(set(core["feats"] + [f + sfx for f in hb["feats"]]))

    merged_subclasses: dict[str, list[str]] = {k: list(v) for k, v in core["subclasses"].items()}
    for cls, names in hb["subclasses"].items():
        # If the parent class is truly homebrew, suffix the key too.
        key = cls + sfx if cls in hb_new_class_set else cls
        suffixed = [n + sfx for n in names]
        merged_subclasses.setdefault(key, []).extend(suffixed)
    for k in merged_subclasses:
        merged_subclasses[k] = sorted(set(merged_subclasses[k]))

    hb_spells_suffixed = [{**s, "name": s["name"] + sfx} for s in hb["spells"]]
    merged_spells = sorted(core["spells"] + hb_spells_suffixed, key=lambda s: s["name"])

    return {
        "classes": merged_classes,
        "species": merged_species,
        "feats": merged_feats,
        "subclasses": merged_subclasses,
        "spells": merged_spells,
    }


_core = _parse_file(_CORE_PATH)
_hb = _parse_file(_HOMEBREW_PATH)
_merged = _merge(_core, _hb)

CLASSES = _merged["classes"]
SPECIES = _merged["species"]
FEATS = _merged["feats"]
SUBCLASSES = _merged["subclasses"]
SPELLS = _merged["spells"]
