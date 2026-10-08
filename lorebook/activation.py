"""Activation engine: given a scan buffer, decide which entries fire for an agent.

Pure logic, no middleware or model concerns.
"""
from dataclasses import dataclass, field

from lorebook.loader import Lorebook
from lorebook.models import Entry, Logic, Visibility
from lorebook.normalizer import normalize


@dataclass
class TraceRecord:
    entry_id: str
    fired: bool = False
    reason: str = ""              # "constant" | "direct" | "recursion" | "secondary_fail" | "visibility" | "budget"
    matched_key: str = ""
    via_recursion: bool = False
    recursion_depth: int = 0
    dropped_budget: bool = False


@dataclass
class ActivationResult:
    activated: list[Entry] = field(default_factory=list)
    trace: list[TraceRecord] = field(default_factory=list)


def activate(book: Lorebook, scan_buffer: str, *, character_id: str) -> ActivationResult:
    settings = book.settings
    entries = book.entries

    normalized_scan = normalize(
        scan_buffer,
        case_sensitive=settings.case_sensitive,
        normalize_unicode=settings.normalize_unicode,
    )

    # ---- Step 1-2: constants + direct keyword hits.
    candidates: dict[str, TraceRecord] = {}
    for entry in entries.values():
        if entry.constant:
            candidates[entry.id] = TraceRecord(entry_id=entry.id, reason="constant")

    for hit in book.matcher.scan(scan_buffer):
        if hit.entry_id not in candidates:
            candidates[hit.entry_id] = TraceRecord(
                entry_id=hit.entry_id, reason="direct", matched_key=hit.key
            )

    # ---- Step 3: secondary-key logic on direct (non-constant) candidates.
    activated: dict[str, TraceRecord] = {}
    skipped: list[TraceRecord] = []
    for entry_id, record in candidates.items():
        entry = entries[entry_id]
        if entry.constant or _secondary_ok(entry, normalized_scan, settings):
            activated[entry_id] = record
        else:
            record.reason = "secondary_fail"
            skipped.append(record)

    # ---- Step 4: recursion up to max_recursion.
    for depth in range(1, settings.max_recursion + 1):
        new_this_pass: list[str] = []
        for entry_id in list(activated.keys()):
            source = entries[entry_id]
            if source.no_recurse_into:
                continue
            for hit in book.matcher.scan(source.content):
                target = entries.get(hit.entry_id)
                if target is None or target.id in activated:
                    continue
                if target.not_triggerable_by_recursion:
                    continue
                if not _secondary_ok(target, normalized_scan, settings):
                    # Recursion still respects secondary gating, evaluated against the
                    # ORIGINAL scan buffer (not the referring entry's content).
                    continue
                new_record = TraceRecord(
                    entry_id=target.id,
                    reason="recursion",
                    matched_key=hit.key,
                    via_recursion=True,
                    recursion_depth=depth,
                )
                activated[target.id] = new_record
                new_this_pass.append(target.id)
        if not new_this_pass:
            break

    # ---- Step 5: visibility filter.
    kept: list[TraceRecord] = []
    for entry_id, record in activated.items():
        entry = entries[entry_id]
        if _visible_to(entry, character_id):
            kept.append(record)
        else:
            record.reason = "visibility"
            skipped.append(record)

    # ---- Step 6: budget. Sort by priority desc, then id for ties.
    kept.sort(key=lambda r: (-entries[r.entry_id].priority, entries[r.entry_id].id))

    result_entries: list[Entry] = []
    used = 0
    dropped: list[TraceRecord] = []
    for record in kept:
        entry = entries[record.entry_id]
        if used + entry.token_count > settings.token_budget and result_entries:
            record.dropped_budget = True
            record.reason = "budget"
            dropped.append(record)
            continue
        record.fired = True
        used += entry.token_count
        result_entries.append(entry)

    trace: list[TraceRecord] = []
    trace.extend(record for record in kept if record.fired)
    trace.extend(dropped)
    trace.extend(skipped)

    return ActivationResult(activated=result_entries, trace=trace)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _secondary_ok(entry: Entry, normalized_scan: str, settings) -> bool:
    """Evaluate secondary_keys against the scan buffer under the entry's logic."""
    if not entry.secondary_keys:
        return True
    norm_keys = [
        normalize(k, case_sensitive=settings.case_sensitive, normalize_unicode=settings.normalize_unicode)
        for k in entry.secondary_keys
    ]
    hits = [k for k in norm_keys if k and k in normalized_scan]
    if entry.secondary_logic == Logic.AND_ANY:
        return bool(hits)
    if entry.secondary_logic == Logic.AND_ALL:
        return len(hits) == len(norm_keys)
    # Logic.NOT
    return not hits


def _visible_to(entry: Entry, character_id: str) -> bool:
    vis = entry.visibility
    if isinstance(vis, list):
        return character_id in vis
    return vis in (Visibility.GLOBAL, Visibility.PARTY)
