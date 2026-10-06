"""Seed a character sheet into the pywf database from a JSON file.

Usage:
    poetry run python scripts/seed_character.py data/characters/thorin.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.characters import Character, CharacterRepository


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: seed_character.py <path-to-character.json>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    character = Character(**data)

    repo = CharacterRepository()
    char_id = repo.upsert(character)
    print(char_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
