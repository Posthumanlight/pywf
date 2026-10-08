# Lorebook

World info authored as one file per entry. The loader walks this directory and
feeds each file through the activation engine on every agent turn: when a key
appears in what the character is about to hear, the entry's body is injected
into that agent's system prompt.

Two formats:

- `*.md` with YAML frontmatter — the frontmatter holds metadata, the body is
  the content that gets injected.
- `*.yaml` — the whole file is a mapping; `content:` is required.

`README.md` and `_book.yaml` are not treated as entries.

## Frontmatter fields

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | str | — | **required**, must be unique across the book |
| `title` | str | `""` | human label, never injected |
| `keys` | list[str] | `[]` | plain-string triggers (Aho-Corasick) |
| `key_regex` | list[str] | `[]` | Python regex triggers |
| `secondary_keys` | list[str] | `[]` | extra gate on top of `keys` |
| `secondary_logic` | `and_any`/`and_all`/`not` | `and_any` | how secondaries combine |
| `constant` | bool | `false` | always active, ignores keys |
| `priority` | int | `0` | higher wins when the token budget is tight |
| `position` | `before`/`after` | `after` | where in the system prompt the entry lands |
| `no_recurse_into` | bool | `false` | don't scan this entry's content for more keys |
| `not_triggerable_by_recursion` | bool | `false` | only direct mentions can trigger this entry |
| `visibility` | `global`/`party`/`[cid,...]` | `global` | per-character gating |

## Book-level settings (`_book.yaml`)

Optional. Omit the file to use the defaults.

```yaml
scan_depth: 1
token_budget: 2000
max_recursion: 3
case_sensitive: false
whole_word: true
normalize_unicode: true
```

## Example

```markdown
---
id: house-veyl
title: House Veyl
keys: ["Veyl"]
secondary_keys: ["House", "duke"]
secondary_logic: and_any
priority: 10
visibility: global
---
House Veyl rules the eastern march. Its sigil is a silver hawk on green.
Known for brutal customs duties and a long rivalry with House Marren.
```

## Hot reload

Edit files freely; call `POST /api/lorebook/reload` to re-read without restarting
the server. `GET /api/lorebook` returns an inventory for debugging.

## Trace

Activation goes through `logging.getLogger("pywf.lorebook")` at INFO (fired or
dropped) and DEBUG (passes with no hits). Watch the server log to confirm what
each agent sees per turn.
