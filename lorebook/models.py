"""Pydantic models for lorebook entries and book-level settings."""
from enum import Enum
from typing import Union

from pydantic import BaseModel, ConfigDict, Field


class Position(str, Enum):
    BEFORE = "before"
    AFTER = "after"


class Logic(str, Enum):
    AND_ANY = "and_any"
    AND_ALL = "and_all"
    NOT = "not"


class Visibility(str, Enum):
    GLOBAL = "global"
    PARTY = "party"


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = ""
    keys: list[str] = Field(default_factory=list)
    key_regex: list[str] = Field(default_factory=list)
    secondary_keys: list[str] = Field(default_factory=list)
    secondary_logic: Logic = Logic.AND_ANY
    constant: bool = False
    priority: int = 0
    position: Position = Position.AFTER
    no_recurse_into: bool = False
    not_triggerable_by_recursion: bool = False
    visibility: Union[Visibility, list[str]] = Visibility.GLOBAL
    content: str

    # Populated by the loader, not authored.
    token_count: int = 0


class BookSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_depth: int = 1
    token_budget: int = 2000
    max_recursion: int = 3
    case_sensitive: bool = False
    whole_word: bool = True
    normalize_unicode: bool = True
