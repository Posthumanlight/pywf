"""Text normalization used for both keys (at load) and scan buffers (per turn)."""
import re
import unicodedata

_WS_RE = re.compile(r"\s+")


def normalize(text: str, *, case_sensitive: bool, normalize_unicode: bool) -> str:
    """NFKC normalize (optional), casefold (unless case-sensitive), collapse whitespace."""
    if normalize_unicode:
        text = unicodedata.normalize("NFKC", text)
    if not case_sensitive:
        text = text.casefold()
    return _WS_RE.sub(" ", text).strip()
