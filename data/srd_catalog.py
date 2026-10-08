"""Enumerate 5.5e SRD content for UI dropdowns.

Parses `data/rules/core_rules.md` and (optionally) `data/rules/homebrew.md`
once at import. Homebrew entries are suffixed with ' (Homebrew)' in their
visible names so they're distinguishable in dropdowns and stored sheets.
Collisions between homebrew and SRD raise `ValueError` at import time.

Also captures the body (prose) of each entry into `BODIES`, keyed by
`(category, display_name)` where `category` is one of
`"class" | "subclass" | "species" | "feat" | "spell"`.

Three progression structures (`CLASS_FEATURES`, `SUBCLASS_FEATURES`,
`SPECIES_FEATURES`) are extracted from the same markdown pass; they power the
"Add features" buttons on the character form. `CLASS_CANTRIPS` is derived from
the existing SPELLS list.
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
_CLASS_FEATURE_RE = re.compile(r"^#### Level (?P<level>\d+): (?P<name>.+?)\s*$")
_SPECIES_FEATURE_RE = re.compile(r"^_\*\*(?P<name>.+?)\.\*\*_")


def _heading_depth(line: str) -> int:
    """Return 1-4 for a markdown ATX heading at depth 1-4, else 0."""
    if not line.startswith("#"):
        return 0
    depth = len(line) - len(line.lstrip("#"))
    if depth == 0 or depth > 6:
        return 0
    if depth >= len(line) or line[depth] != " ":
        return 0
    return depth


def _extract_class_features(body_lines: list[str], class_name: str) -> dict[int, list[str]]:
    """Pull `#### Level N: Name` from the `### <Class> Class Features` section only.

    Guard against features living inside a `### <Class> Subclass: ...` section
    further down the body — those are the subclass's, not the class's.
    """
    target = f"### {class_name} Class Features"
    in_section = False
    section_depth = 0
    out: dict[int, list[str]] = {}
    for raw in body_lines:
        line = raw.rstrip()
        depth = _heading_depth(line)
        if line == target:
            in_section = True
            section_depth = depth
            continue
        if in_section and depth and depth <= section_depth:
            break
        if in_section:
            m = _CLASS_FEATURE_RE.match(line)
            if m:
                level = int(m.group("level"))
                out.setdefault(level, []).append(m.group("name").strip())
    return out


def _extract_subclass_features(body_lines: list[str]) -> dict[int, list[str]]:
    """Pull `#### Level N: Name` from a subclass body (the whole body IS the feature list)."""
    out: dict[int, list[str]] = {}
    for raw in body_lines:
        m = _CLASS_FEATURE_RE.match(raw.rstrip())
        if m:
            level = int(m.group("level"))
            out.setdefault(level, []).append(m.group("name").strip())
    return out


def _extract_species_features(body_lines: list[str]) -> list[str]:
    """Pull `_**Name.**_` from a species body."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in body_lines:
        m = _SPECIES_FEATURE_RE.match(raw.rstrip())
        if m:
            name = m.group("name").strip()
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def _parse_file(path: Path) -> dict:
    """Parse one SRD-formatted markdown file. Returns a dict with keys
    'classes', 'species', 'feats', 'subclasses', 'spells', 'bodies',
    'class_features', 'subclass_features', 'species_features'.
    Returns empty collections if the file does not exist or is empty.
    """
    empty: dict = {
        "classes": [],
        "species": [],
        "feats": [],
        "subclasses": {},
        "spells": [],
        "bodies": {},
        "class_features": {},
        "subclass_features": {},
        "species_features": {},
    }
    if not path.exists():
        return empty

    lines = path.read_text(encoding="utf-8").splitlines()

    classes: list[str] = []
    species: list[str] = []
    feats: list[str] = []
    subclasses: dict[str, list[str]] = {}
    spells: list[dict] = []
    subclass_parent: dict[str, str] = {}

    # (category, name, start_line_idx, depth)
    entries: list[tuple[str, str, int, int]] = []
    headings: list[tuple[int, int]] = []

    h1 = h2 = h3 = ""
    current_class = ""
    pending_spell: str | None = None
    pending_spell_start = -1

    for i, raw in enumerate(lines):
        line = raw.rstrip()
        depth = _heading_depth(line)
        if depth:
            headings.append((i, depth))

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
                    entries.append(("class", h2, i, 2))
                current_class = h2
            else:
                current_class = ""
            continue

        if line.startswith("### "):
            h3 = line[4:].strip()
            m = _SUBCLASS_RE.match(line)
            if m and h1 == "Classes" and current_class:
                subname = m.group("name").strip()
                subclasses.setdefault(current_class, []).append(subname)
                subclass_parent[subname] = current_class
                entries.append(("subclass", subname, i, 3))
                continue
            if h2 == "Spell Descriptions":
                pending_spell = h3
                pending_spell_start = i
            continue

        if line.startswith("#### "):
            name = line[5:].strip()
            if h2 == "Character Species" and h3 == "Species Descriptions":
                species.append(name)
                entries.append(("species", name, i, 4))
            elif h2 == "Feat Descriptions":
                feats.append(name)
                entries.append(("feat", name, i, 4))
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
                entries.append(("spell", pending_spell, pending_spell_start, 3))
                pending_spell = None
                pending_spell_start = -1

    # Compute body ranges + feature extraction in a single pass over entries.
    bodies: dict[tuple[str, str], str] = {}
    class_features: dict[str, dict[int, list[str]]] = {}
    subclass_features: dict[str, dict[int, list[str]]] = {}
    species_features: dict[str, list[str]] = {}

    for cat, name, start, depth in entries:
        end = len(lines)
        for h_idx, h_depth in headings:
            if h_idx > start and h_depth <= depth:
                end = h_idx
                break
        body_lines = lines[start:end]
        bodies[(cat, name)] = "\n".join(body_lines).strip("\n")

        if cat == "class":
            class_features[name] = _extract_class_features(body_lines, name)
        elif cat == "subclass":
            parent = subclass_parent.get(name, "")
            key = f"{parent}: {name}" if parent else name
            subclass_features[key] = _extract_subclass_features(body_lines)
        elif cat == "species":
            species_features[name] = _extract_species_features(body_lines)

    return {
        "classes": classes,
        "species": species,
        "feats": feats,
        "subclasses": subclasses,
        "spells": spells,
        "bodies": bodies,
        "class_features": class_features,
        "subclass_features": subclass_features,
        "species_features": species_features,
    }


def _merge(core: dict, hb: dict) -> dict:
    """Combine SRD + homebrew. Raises ValueError on leaf-name collisions.

    `## <Class>` headings in homebrew that already exist in SRD are treated as
    *parent context* (so the author can declare `## Fighter` only to attach a
    new subclass to SRD Fighter), not as new classes — no collision there.
    Collisions are reported for subclasses, species, feats, and spells.
    """
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
        key = cls + sfx if cls in hb_new_class_set else cls
        suffixed = [n + sfx for n in names]
        merged_subclasses.setdefault(key, []).extend(suffixed)
    for k in merged_subclasses:
        merged_subclasses[k] = sorted(set(merged_subclasses[k]))

    hb_spells_suffixed = [{**s, "name": s["name"] + sfx} for s in hb["spells"]]
    merged_spells = sorted(core["spells"] + hb_spells_suffixed, key=lambda s: s["name"])

    # Bodies: SRD keys stay raw; homebrew keys get the display suffix.
    merged_bodies: dict[tuple[str, str], str] = dict(core["bodies"])
    for (cat, name), body in hb["bodies"].items():
        if cat == "class" and name in core_class_set:
            continue
        display_name = name + sfx
        merged_bodies[(cat, display_name)] = body

    # Class features: homebrew's parent-context classes have empty extraction, skip them;
    # truly-new homebrew classes get the suffix.
    merged_class_features: dict[str, dict[int, list[str]]] = dict(core["class_features"])
    for name, feats_by_level in hb["class_features"].items():
        if not feats_by_level and name in core_class_set:
            continue
        key = name + sfx if name in hb_new_class_set else name
        merged_class_features[key] = feats_by_level

    # Subclass features are keyed by "<Class>: <Subclass>" with class+subclass potentially suffixed.
    merged_subclass_features: dict[str, dict[int, list[str]]] = dict(core["subclass_features"])
    for key, feats_by_level in hb["subclass_features"].items():
        parent, _, subname = key.partition(": ")
        parent_key = parent + sfx if parent in hb_new_class_set else parent
        new_key = f"{parent_key}: {subname + sfx}"
        merged_subclass_features[new_key] = feats_by_level

    merged_species_features: dict[str, list[str]] = dict(core["species_features"])
    for name, feats in hb["species_features"].items():
        merged_species_features[name + sfx] = feats

    return {
        "classes": merged_classes,
        "species": merged_species,
        "feats": merged_feats,
        "subclasses": merged_subclasses,
        "spells": merged_spells,
        "bodies": merged_bodies,
        "class_features": merged_class_features,
        "subclass_features": merged_subclass_features,
        "species_features": merged_species_features,
    }


_core = _parse_file(_CORE_PATH)
_hb = _parse_file(_HOMEBREW_PATH)
_merged = _merge(_core, _hb)

CLASSES = _merged["classes"]
SPECIES = _merged["species"]
FEATS = _merged["feats"]
SUBCLASSES = _merged["subclasses"]
SPELLS = _merged["spells"]
BODIES = _merged["bodies"]
CLASS_FEATURES = _merged["class_features"]
SUBCLASS_FEATURES = _merged["subclass_features"]
SPECIES_FEATURES = _merged["species_features"]


def _build_class_cantrips(spells: list[dict]) -> dict[str, list[str]]:
    """`CLASS_CANTRIPS[class]` = sorted cantrip names available to that class."""
    out: dict[str, list[str]] = {}
    for spell in spells:
        if spell.get("level") != 0:
            continue
        for cls in spell.get("classes") or []:
            out.setdefault(cls, []).append(spell["name"])
    for cls in out:
        out[cls] = sorted(set(out[cls]))
    return out


CLASS_CANTRIPS: dict[str, list[str]] = _build_class_cantrips(SPELLS)


def get_body(category: str, name: str) -> str | None:
    """Return the SRD/homebrew body text for `(category, name)`, or None.

    Tolerates the ' (Homebrew)' suffix: tries both suffixed and unsuffixed
    forms so callers don't have to care which they have.
    """
    name = (name or "").strip()
    if not name:
        return None
    if (category, name) in BODIES:
        return BODIES[(category, name)]
    if name.endswith(_HOMEBREW_SUFFIX):
        trunc = name[: -len(_HOMEBREW_SUFFIX)]
        if (category, trunc) in BODIES:
            return BODIES[(category, trunc)]
    else:
        if (category, name + _HOMEBREW_SUFFIX) in BODIES:
            return BODIES[(category, name + _HOMEBREW_SUFFIX)]
    return None
