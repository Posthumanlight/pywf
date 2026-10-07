"""pywf entry point: dispatches to CLI REPL or FastAPI server based on settings."""
from langgraph.checkpoint.sqlite import SqliteSaver

from db.core import DB_PATH
from engine.core import (
    MissingCharactersError,
    PartyContext,
    UnknownTargetError,
    build_party,
    parse_dm_line,
    run_round,
)
from settings.settings import settings


def _print_banner(ctx: PartyContext) -> None:
    roster = ", ".join(f"{ctx.names[cid]} (@{cid})" for cid in ctx.party_ids)
    print(f"pywf — party: {roster}")
    print("Type DM narration / direct address. Mark your OOC lines with [OOC: ...].")
    print("Prefix with @<id> to speak to one party member (e.g. '@thorin ...').")
    print("Commands: /exit, /quit")
    print()


def run_cli() -> int:
    with SqliteSaver.from_conn_string(str(DB_PATH)) as saver:
        try:
            ctx = build_party(saver)
        except MissingCharactersError as exc:
            print(exc)
            print(f"Available ids: {exc.available}")
            print("Seed one with: poetry run python scripts/seed_character.py <path-to-json>")
            return 1
        except ValueError as exc:
            print(exc)
            return 1

        _print_banner(ctx)

        while True:
            try:
                line = input("DM> ")
            except (EOFError, KeyboardInterrupt):
                print()
                return 0

            prompt = line.strip()
            if not prompt:
                continue
            if prompt.lower() in ("/exit", "/quit"):
                return 0

            try:
                parsed = parse_dm_line(prompt, ctx.party_ids)
            except UnknownTargetError as exc:
                print(exc)
                continue

            for turn in run_round(ctx, parsed.dm_text, parsed.order):
                print()
                print(f"{turn['name']}> {turn['text']}")
                print()


def run_api() -> int:
    import uvicorn

    uvicorn.run("api.app:app", host=settings.api_host, port=settings.api_port)
    return 0


def main() -> int:
    if settings.interface == "api":
        return run_api()
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
