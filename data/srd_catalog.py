"""Enumerate 5.5e SRD content for UI dropdowns.

Parses `data/rules/core_rules.md` once at import; exposes alphabetised lists.
"""
import re
from pathlib import Path

from settings.settings import settings

_SRD_PATH = settings.BASE_PATH / "data" / "rules" / "core_rules.md"

_SPELL_META_RE = re.compile(
    r"^_(?:Level (?P<level>\d+) )?(?P<school>[A-Za-z]+)(?P<cantrip> Cantrip)?(?: \((?P<classes>[^)]+)\))?_\s*$"
)
_SUBCLASS_RE = re.compile(r"^### (?P<class>\S[^:]*?) Subclass:\s+(?P<name>.+?)\s*$")


def _parse() -> tuple[list[str], list[str], list[str], dict[str, list[str]], list[dict]]:
    classes: list[str] = []
    species: list[str] = []
    feats: list[str] = []
    subclasses: dict[str, list[str]] = {}
    spells: list[dict] = []

    h1 = h2 = h3 = ""
    current_class = ""
    pending_spell: str | None = None

    for raw in _SRD_PATH.read_text(encoding="utf-8").splitlines():
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
                classes.append(h2)
                current_class = h2
            else:
                current_class = ""
            continue

        if line.startswith("### "):
            h3 = line[4:].strip()
            # Subclass headings inside a class section.
            m = _SUBCLASS_RE.match(line)
            if m and h1 == "Classes" and current_class:
                subclasses.setdefault(current_class, []).append(m.group("name").strip())
                continue
            # Spell entries live under ## Spell Descriptions.
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

    species.sort()
    feats.sort()
    spells.sort(key=lambda s: s["name"])
    for cls in subclasses:
        subclasses[cls].sort()
    # Classes left in SRD order (Barbarian…Wizard) — it's already alphabetical in the SRD.

    return classes, species, feats, subclasses, spells


CLASSES, SPECIES, FEATS, SUBCLASSES, SPELLS = _parse()
