# pywf — AI players for TTRPG

## What this project is

`pywf` is a Python app that provides **AI player-character agents** for Dungeons & Dragons 5e. The agents play *as players at the table*, under a (currently human) Dungeon Master's authority. See [data/prompts/system_prompt.py](data/prompts/system_prompt.py) for the full role contract — the agent controls only its own character, never narrates outcomes, and marks every out-of-character message with `[OOC: ...]`.

## Goals and roadmap

- **Scope:** support a **party of multiple AI player agents** collaborating under a human DM. Not an AI DM, not a single-player tool, no multi-DM.
- **Runtime surfaces:**
  1. ✅ **CLI chat loop** — shipped. [main.py](main.py) dispatches to `run_cli()`; `/exit`, `/quit`, `/memory` commands supported.
  2. ✅ **FastAPI service** — shipped. Landing, chat (inline party picker + clickable player names → sheet editor), character CRUD, memory stats, lorebook introspection/reload.
  3. ⏳ **Discord / Telegram bot** — next; `aiogram` is the current favorite for Telegram.
- **Shipped subsystems:**
  - `MemoryMiddleware` with rolling episode summaries + a chronicle, backed by `SqliteStore`.
  - Lorebook ([lorebook/](lorebook/)): keyword-triggered world info with YAML-frontmatter markdown entries under [data/lore/](data/lore/), hot-reloadable via `POST /api/lorebook/reload`.
  - Character CRUD: JSON API + Alpine/HTMX form page with SRD-driven dropdowns and a sticky SRD-rules sidebar.
  - Agent caching + shared chat models (lifespan builds the models once; `app.state.agent_cache` is keyed by `(cid, frozenset(peers))`).
  - `LoggingModelFallbackMiddleware` + `model_timeout_s` + graceful "error turn" in `run_round` when every model is exhausted.

## Stack

- Python `>=3.12`, Poetry for dependency management ([pyproject.toml](pyproject.toml))
- **LangChain 1.x** (`langchain.agents.create_agent`) + **LangGraph** for the agent runtime
- **Google Gemini** via `langchain-google-genai` for chat and embeddings
- **sqlite-vec** vector store for SRD retrieval, plus a plain **SQLite** table for character sheets (both in [data/pywf.db](data/pywf.db))
- **FastAPI** + `uvicorn[standard]` for the API surface
- **pyahocorasick** + **PyYAML** for the lorebook keyword index and frontmatter parsing
- `pydantic-settings` + `python-dotenv` for config

Env config lives in `.env` at the repo root; `gemini_api_key` is required. Currently supported settings ([settings/settings.py](settings/settings.py)): `gemini_api_key`, `character_ids` (CSV), `model_fallbacks` (CSV), `model_timeout_s`, `memory_model`, `memory_trigger_rounds`, `memory_keep_rounds`, `memory_max_episodes`, `interface` (`cli`/`api`), `api_host`, `api_port`.

## Layout

```
agent/         LangChain agent factory + middleware (memory, fallback) + tools
api/           FastAPI app, lifespan, routers (characters, party, srd, lorebook, pages)
engine/        PartyContext, build_party, parse_dm_line, run_round — shared by CLI and API
lorebook/      Keyword-triggered world info: models, loader, matcher, activation, middleware
db/            SQLite setup (DB_PATH) + CharacterRepository
data/          Prompts, SRD rules (core + homebrew), lorebook entries, SRD catalog, pywf.db
settings/      Pydantic Settings loaded from .env
scripts/       Dev-time helpers: seed_character, ingest_srd, inspect_form_page, verify_*
main.py        CLI/API dispatcher reads settings.interface
```

## How the pieces fit

1. **Startup.** [main.py](main.py) reads `settings.interface`; either `run_cli()` or `run_api()` (uvicorn against `api.app:app`). The FastAPI lifespan opens one `SqliteSaver` + `SqliteStore`, pre-builds `chat_model` / `memory_model` / `fallback_models` via `init_chat_model(..., timeout=settings.model_timeout_s)` once, loads the lorebook from [data/lore/](data/lore/), and seeds the initial party from `settings.character_ids` by calling `build_party(...)`.
2. **Picking a party (API).** `POST /api/party` validates ids against `CharacterRepository.list_ids()`, calls `build_party(..., agent_cache=app.state.agent_cache)` which reuses cached agents when `(cid, frozenset(peers))` is already in the cache.
3. **A round.** `POST /chat` → `parse_dm_line` (handles `@id`-targeting) → `run_round` iterates the party in order. Each agent's `invoke` runs through the middleware stack: `MemoryMiddleware` (appends chronicle + episodes to the system prompt) → `LorebookMiddleware` (scans the latest `HumanMessage`, injects matching entries) → `LoggingModelFallbackMiddleware` (catches any `Exception`, tries fallbacks, logs each attempt) → the Gemini client.
4. **Tool calls.** The agent can call `rules_srd_retriever` (RAG over `data/rules/*.md` via sqlite-vec), `get_character_sheet` (reads `CharacterRepository`), and `roll_dice` (numpy-backed).
5. **Error turn.** If the fallback chain is exhausted, `run_round` catches the exception, appends `Turn(text="[error: ...]")`, logs via `pywf.engine`, and halts the round. The browser renders that like any other turn.
6. **Memory archival.** When a character's thread crosses `memory_trigger_rounds`, `MemoryMiddleware.before_agent` summarizes old rounds into an episode in the `SqliteStore`; when episodes exceed `memory_max_episodes`, the oldest fold into a single `chronicle`.

## Current gotchas

- **The Google genai AFC warning is cosmetic.** `Direct use of automatic function calling in Models.generate_content is not recommended...` fires because langchain hands `tools=` to the Gemini SDK while running the loop itself; it's a false positive, not a bug.
- **`model_timeout_s` depends on `ChatGoogleGenerativeAI` honoring the `timeout` kwarg.** If the SDK ignores it on an outage, hangs may still happen. The fallback plan is an `asyncio.wait_for` wrapper; not implemented today.
- **Lorebook MVP defers sticky, cooldown, SQLite trace, and `at-depth-N` position.** `BookSettings.scan_depth` exists but the scan buffer is currently always just the latest `HumanMessage`.
- **Peer names are baked into the system prompt.** `build_player_system_prompt(cid, party_member_names)` embeds the roster, so the agent cache key is `(cid, frozenset(peer_names))`. Changing party composition rebuilds agents for new peer sets — do not weaken the key to just `cid`.
- **Gemini client bootstrap is expensive (seconds).** Models are pre-built once in lifespan and reused via `build_party(chat_model=..., memory_model=..., fallback_models=..., agent_cache=...)`. Don't regress by passing model-name strings on a hot path — `init_chat_model` on a request is what caused the original 5–10 s Start-Session latency.

## Working rules for Claude in this repo

- **Minimal diffs.** No drive-by reformatting, no renames unless requested.
- **Ask before refactoring.** If a change wants to grow beyond the stated scope, surface the proposal first.
- **Drive-by bug fixes are welcome** when they sit directly in the code being changed — just mention them in the response.
- **PowerShell is the default shell** (Windows). Use `$env:VAR`, `$null`, backtick continuations; no bash-isms in commands shown to the user.
- The repo is on branch `main`. A stale `master` ref also exists in `.git/refs/heads/`; ignore it unless cleanup is requested.
