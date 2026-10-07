# pywf — AI players for TTRPG

## What this project is

`pywf` is a Python app that provides **AI player-character agents** for Dungeons & Dragons 5e. The agents play *as players at the table*, under a (currently human) Dungeon Master's authority. See [data/prompts/system_prompt.py](data/prompts/system_prompt.py) for the full role contract — the agent controls only its own character, never narrates outcomes, and marks every out-of-character message with `[OOC: ...]`.

## Goals and roadmap

- **Scope:** support a **party of multiple AI player agents** collaborating under a human DM. Not an AI DM, not a single-player tool.
- **Runtime surfaces (in order):**
  1. **CLI chat loop** — first milestone. `main.py` is currently an empty placeholder; the entry point still needs to be built.
  2. **FastAPI service** — expose the agent(s) over HTTP for frontends / VTTs.
  3. **Discord / Telegram bot** — likely via `aiogram` for Telegram.

## Stack

- Python `>=3.12`, Poetry for dependency management ([pyproject.toml](pyproject.toml))
- **LangChain 1.x** (`langchain.agents.create_agent`) + **LangGraph** for the agent runtime
- **Google Gemini** via `langchain-google-genai` for both chat and embeddings
- **sqlite-vec** vector store for SRD retrieval, plus a plain **SQLite** table for character sheets (both in [data/pywf.db](data/pywf.db))
- `pydantic-settings` + `python-dotenv` for config

Env config lives in `.env` at the repo root; `GEMINI_API_KEY` is required ([settings/settings.py](settings/settings.py)).

## Layout

- [agent/core/agent.py](agent/core/agent.py) — builds the `player_agent` with the system prompt and tool set.
- [agent/core/memory.py](agent/core/memory.py) — `MemoryMiddleware`: archives old rounds of a character's thread into a LangGraph `SqliteStore` (namespace `("memories", <character_id>)`: rolling `episode:*` summaries + one `chronicle`) and injects them into the system prompt. Thresholds live in `settings` (`memory_*`). Stats via CLI `/memory` or `GET /memory`.
- [agent/tools/](agent/tools/) — tools exposed to the agent:
  - [srd_rules_retriever.py](agent/tools/srd_rules_retriever.py) — RAG over SRD markdown via sqlite-vec + Gemini embeddings.
  - [get_character_sheet.py](agent/tools/get_character_sheet.py) — reads a character sheet by id from SQLite.
  - [roll_dice.py](agent/tools/roll_dice.py) — numpy-backed dice roller with advantage/disadvantage.
- [db/core.py](db/core.py) — resolves `DB_PATH`.
- [db/characters.py](db/characters.py) — `CharacterRepository` (schema init, upsert SQL, lookup, delete). Scalar vs. JSON column split lives here.
- [data/rules/](data/rules/) — SRD markdown. Treat as the source of truth for rules content; chunked and embedded by the retriever.
- [data/prompts/system_prompt.py](data/prompts/system_prompt.py) — the player-agent system prompt (long and prescriptive; read it before changing agent behavior).
- [settings/settings.py](settings/settings.py) — `Settings` with `BASE_PATH` and `gemini_api_key`.

## How the pieces fit

1. On import, `srd_rules_retriever` loads every `.md` under `data/rules/`, splits by markdown headers then by ~800-char chunks, and wraps a `SQLiteVec` retriever as a LangChain `retriever_tool`.
2. `agent/core/agent.py` wires `rules_srd_retriever`, `roll_dice`, and `get_character_sheet` into a `create_agent(...)` instance with the player system prompt.
3. The character sheet tool queries `CharacterRepository` by id and returns JSON with the structured fields (classes, spells, equipment, etc.) deserialized.

## Known rough edges (worth fixing)

These were flagged during the first review pass — not blockers for understanding the project, but important context before relying on current behavior:

- **Bad Gemini model id.** [agent/core/agent.py:8](agent/core/agent.py#L8) uses `"google_genai:gemini-3.7-flash"` — no such version exists. Likely intended `gemini-2.5-flash` (or the latest available flash model).
- **SRD vector store is never populated.** [agent/tools/srd_rules_retriever.py](agent/tools/srd_rules_retriever.py) loads, splits, and *constructs* embeddings/vectorstore, but never calls `vectorstore.add_documents(chunks)` — so the retriever queries an empty table. Also: running the full load+embed on every import is expensive; this should be a one-time ingestion step (separate script or guarded by a "table empty" check).
- **SQL injection + bad quoting in character lookup.** [db/characters.py:99](db/characters.py#L99) uses `f"SELECT * FROM characters WHERE id = {char_id}"`. Needs to be `conn.execute("SELECT * FROM characters WHERE id = ?", (char_id,))`. Current form will crash on any non-numeric id (which is always, since `id` is TEXT).
- **`list_ids` called as attribute, not method.** [agent/tools/get_character_sheet.py:19](agent/tools/get_character_sheet.py#L19) does `char_db.list_ids` — missing parentheses, so the "not found" branch returns a bound-method repr instead of the id list.
- **Shape mismatch.** `get_characters_json` returns a JSON *list* (even for a single id), but the tool docstring and callers treat it as a single sheet. Also returns `"[]"` rather than `None` when the id is unknown, so the `is None` check in the tool never fires.

## Working rules for Claude in this repo

- **Minimal diffs.** No drive-by reformatting, no renames unless requested.
- **Ask before refactoring.** If a change wants to grow beyond the stated scope, surface the proposal first.
- **Drive-by bug fixes are welcome** when they sit directly in the code being changed — just mention them in the response.
- **PowerShell is the default shell** (Windows). Use `$env:VAR`, `$null`, backtick continuations; no bash-isms in commands shown to the user.
- The repo is on branch `main`. A stale `master` ref also exists in `.git/refs/heads/`; ignore it unless cleanup is requested.
