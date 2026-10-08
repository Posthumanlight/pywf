"""Aho-Corasick + regex matcher over normalized lorebook keys."""
import re
from dataclasses import dataclass
from typing import Iterable

import ahocorasick

from lorebook.models import BookSettings, Entry
from lorebook.normalizer import normalize


@dataclass(frozen=True)
class Hit:
    entry_id: str
    key: str
    span: tuple[int, int]


_WORD_RE = re.compile(r"\w", re.UNICODE)


def _is_word(ch: str) -> bool:
    return bool(_WORD_RE.match(ch))


def _at_word_boundaries(text: str, start: int, end: int) -> bool:
    """True iff positions start..end are flanked by non-word chars or string ends."""
    left_ok = start == 0 or not _is_word(text[start - 1])
    right_ok = end == len(text) or not _is_word(text[end])
    return left_ok and right_ok


class Matcher:
    """Normalized-key index over a set of entries.

    Call `scan(text)` with raw text; it normalizes with the book settings and
    returns the list of hits (de-duplicated per (entry_id, key, span)).
    """

    def __init__(self, entries: Iterable[Entry], settings: BookSettings) -> None:
        self.settings = settings
        self._automaton = ahocorasick.Automaton()
        self._regex: list[tuple[str, re.Pattern[str]]] = []
        self._has_automaton = False

        # Multiple entries can share a normalized key; the automaton holds one payload per node,
        # so the payload is the list of all (entry_id, key) pairs that terminate there.
        key_payload: dict[str, list[tuple[str, str]]] = {}
        for entry in entries:
            for raw_key in entry.keys:
                nkey = normalize(
                    raw_key,
                    case_sensitive=settings.case_sensitive,
                    normalize_unicode=settings.normalize_unicode,
                )
                if nkey:
                    key_payload.setdefault(nkey, []).append((entry.id, nkey))
            for raw_rx in entry.key_regex:
                flags = 0 if settings.case_sensitive else re.IGNORECASE
                self._regex.append((entry.id, re.compile(raw_rx, flags)))

        for nkey, pairs in key_payload.items():
            self._automaton.add_word(nkey, pairs)
            self._has_automaton = True

        if self._has_automaton:
            self._automaton.make_automaton()

    def scan(self, text: str) -> list[Hit]:
        normalized = normalize(
            text,
            case_sensitive=self.settings.case_sensitive,
            normalize_unicode=self.settings.normalize_unicode,
        )
        hits: list[Hit] = []
        seen: set[tuple[str, str, int, int]] = set()

        if self._has_automaton and normalized:
            for end_index, pairs in self._automaton.iter(normalized):
                for entry_id, key in pairs:
                    start = end_index - len(key) + 1
                    end = end_index + 1
                    if self.settings.whole_word and not _at_word_boundaries(normalized, start, end):
                        continue
                    dedup_key = (entry_id, key, start, end)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    hits.append(Hit(entry_id=entry_id, key=key, span=(start, end)))

        # Regex keys run on the raw text so authors can anchor on casing / punctuation
        # with their own flags; keeping them separate from the normalized AC pass.
        for entry_id, pattern in self._regex:
            for m in pattern.finditer(text):
                dedup_key = (entry_id, f"re:{pattern.pattern}", m.start(), m.end())
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                hits.append(Hit(entry_id=entry_id, key=m.group(0), span=(m.start(), m.end())))

        return hits
