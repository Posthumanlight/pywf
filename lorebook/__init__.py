"""Lorebook: keyword-triggered world info injected into agent prompts.

Public surface: `load(path)` returns a `Lorebook`; `LorebookMiddleware(cid, book)`
wraps it as a langchain agent middleware. All matching/activation is pure Python
and doesn't touch Gemini.
"""
from lorebook.loader import LorebookValidationError, load
from lorebook.middleware import LorebookMiddleware
from lorebook.models import BookSettings, Entry, Logic, Position, Visibility

__all__ = [
    "BookSettings",
    "Entry",
    "Logic",
    "LorebookMiddleware",
    "LorebookValidationError",
    "Position",
    "Visibility",
    "load",
]
