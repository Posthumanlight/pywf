from langchain_core.tools import tool
import json
from db.characters import CharacterRepository

@tool(parse_docstring=True)
def get_character_sheet(character_id: str) -> str:
    """Get the full D&D character sheet as JSON.

    Args:
        character_id: Unique ID of the character, e.g. "thorin".
    """
    char_db = CharacterRepository()
    character = char_db.get_characters_json(char_id=character_id)
    if character is None:
        return json.dumps(
            {
                "error": f"Character '{character_id}' not found.",
                "available_ids": char_db.list_ids,
            },
            ensure_ascii=False,
        )

    return character