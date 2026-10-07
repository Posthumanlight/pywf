<!--
Homebrew content for pywf. Parsed by data/srd_catalog.py (same walker as core_rules.md).

Rules of the road:
- Keep the exact heading hierarchy below. Only the real headings (left-aligned, column 0)
  are parsed; anything inside this comment or indented by at least one space is ignored.
- To add a SUBCLASS to an SRD class, re-open that class under `# Classes` with a `## <Class>`
  heading (just the heading is enough — it's treated as *parent context*, not a redefinition),
  then add `### <Class> Subclass: <Name>`.
- To add a BRAND-NEW class, use `## <Class>`; its name becomes `<Class> (Homebrew)` in the UI.
- Spells require the metadata line immediately below the `### <Name>` heading, e.g.
  `_Level 4 Evocation (Wizard)_` or `_Evocation Cantrip (Sorcerer)_`.
- Any name collision with SRD (same species/feat/spell name, or same subclass under the same
  parent) fails the server at import time with a clear ValueError.
- After editing, restart the FastAPI/CLI process. For RAG citation support, also run:
  `poetry run python scripts/ingest_srd.py`.

Examples (shown indented so the parser skips them):

  ## Blood Hunter

  ### Blood Hunter Subclass: Order of the Lycan

  ## Fighter

  ### Fighter Subclass: Blade Master

  #### Shardkin

  #### Lucky Streak

  ### Superfireball

  _Level 4 Evocation (Wizard)_
-->

# Classes


# Character Origins

## Character Backgrounds


## Character Species

### Species Descriptions


# Feats

## Feat Descriptions


# Spells

## Spell Descriptions
