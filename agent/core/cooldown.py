"""Per-model cooldown registry triggered by rate-limit / quota exceptions.

A chat model instance built through `build_chat_model` registers itself here
with its spec string (e.g. `google_genai:gemini-3.7-flash`). When the fallback
middleware observes a 429-style error, it calls `start_cooldown`, which records
a cooldown-until timestamp keyed by that spec. Future requests that touch the
same model skip it via `is_on_cooldown` until the timestamp passes.

Resolution order for cooldown duration:
    1. YAML override in settings/model_cooldowns.yaml (admin-set, authoritative)
    2. retry hint parsed from the exception (`retry_delay` / `Retry-After`)
    3. 8-hour default (28800 s)
"""
import logging
import re
import threading
import time
from typing import Any

import yaml

from settings.settings import settings

logger = logging.getLogger("pywf.cooldown")

_DEFAULT_SECONDS = 8 * 3600
_YAML_PATH = settings.BASE_PATH / "settings" / "model_cooldowns.yaml"

_lock = threading.Lock()
_specs: dict[int, str] = {}
_until: dict[str, float] = {}


def _load_overrides() -> dict[str, int]:
    if not _YAML_PATH.exists():
        return {}
    with _YAML_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        logger.warning("model_cooldowns.yaml: expected a top-level mapping")
        return {}
    out: dict[str, int] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            logger.warning("model_cooldowns.yaml: bad value for %r: %r", k, v)
    return out


_overrides: dict[str, int] = _load_overrides()


def register_model(model: Any, spec: str) -> None:
    """Associate a built chat model with its spec string."""
    _specs[id(model)] = spec


def spec_for(model: Any) -> str | None:
    return _specs.get(id(model))


def is_on_cooldown(model: Any) -> bool:
    spec = spec_for(model)
    if spec is None:
        return False
    with _lock:
        expiry = _until.get(spec)
        if expiry is None:
            return False
        if time.monotonic() >= expiry:
            _until.pop(spec, None)
            return False
    return True


def start_cooldown(model: Any, exc: Exception) -> int | None:
    spec = spec_for(model)
    if spec is None:
        return None
    seconds = _resolve_duration(spec, exc)
    with _lock:
        _until[spec] = time.monotonic() + seconds
    return seconds


def is_quota_error(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in {"ResourceExhausted", "RateLimitError"}:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "quota" in msg


def snapshot() -> dict[str, dict]:
    """Current active cooldowns, for the /api/cooldowns debug endpoint."""
    now = time.monotonic()
    with _lock:
        active = {spec: expiry for spec, expiry in _until.items() if expiry > now}
    return {
        spec: {"remaining_s": round(expiry - now, 1), "override": spec in _overrides}
        for spec, expiry in active.items()
    }


def _resolve_duration(spec: str, exc: Exception) -> int:
    """YAML override wins; else parse the exception; else 8-hour default."""
    if spec in _overrides:
        return _overrides[spec]
    hint = _extract_retry_delay(exc)
    if hint is not None and hint > 0:
        return hint
    return _DEFAULT_SECONDS


def _extract_retry_delay(exc: Exception) -> int | None:
    # Google api_core: ResourceExhausted carries RetryInfo in .retry_delay (Duration-like).
    rd = getattr(exc, "retry_delay", None)
    if rd is not None:
        secs = getattr(rd, "seconds", None)
        if secs is not None:
            try:
                return int(secs)
            except (TypeError, ValueError):
                pass
    # OpenAI SDK: exc.response.headers has Retry-After.
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
        if headers is not None and hasattr(headers, "get"):
            for key in ("retry-after", "Retry-After"):
                try:
                    value = headers.get(key)
                except Exception:
                    value = None
                if value:
                    try:
                        return int(float(value))
                    except (TypeError, ValueError):
                        pass
    # Fallback: scan the message for "retry in Xs" / "retry after Xs".
    m = re.search(r"retry (?:in|after)\s+(\d+)", str(exc), re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None
