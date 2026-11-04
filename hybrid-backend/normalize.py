from __future__ import annotations

import re

_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[A-Za-z0-9]+")
_VENDOR_NOISE = frozenset(
    {
        "pvt",
        "ltd",
        "limited",
        "private",
        "corp",
        "corporation",
        "co",
        "company",
        "llp",
        "inc",
        "ms",
        "the",
        "and",
    }
)
_SPEC = re.compile(
    r"\b\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?(?:\s*(?:mm|cm|mtr|m|nb|swg|awg|amp|kg))?\b",
    re.IGNORECASE,
)

_VENDOR_EXPANSIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bpvt\b"), "private"),
    (re.compile(r"\bltd\b"), "limited"),
    (re.compile(r"\bcorp\b"), "corporation"),
    (re.compile(r"\bengg\b"), "engineering"),
    (re.compile(r"\bco\b"), "company"),
)

_MATERIAL_EXPANSIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsch\b"), "schedule"),
    (re.compile(r"\bdia\b"), "diameter"),
    (re.compile(r"\bss\b"), "stainless steel"),
    (re.compile(r"\bms\b"), "mild steel"),
    (re.compile(r"\bnb\b"), "nominal bore"),
    (re.compile(r"\bupvc\b"), "upvc"),
    (re.compile(r"\bpvc\b"), "pvc"),
)


def lexical_query(text: str, entity_type: str) -> str:
    """Drop legal suffixes so a query like 'wipro ltd' is not flooded by every Ltd."""
    if entity_type != "vendor":
        return text.strip()
    kept = [token for token in _TOKEN.findall(text) if token.lower() not in _VENDOR_NOISE]
    return " ".join(kept) if kept else text.strip()


def normalize_query(text: str, entity_type: str) -> str:
    """Expand stable abbreviations for the embedding query. Lexical search keeps the raw text."""
    cleaned = _PUNCT.sub(" ", text.lower())
    cleaned = _SPACE.sub(" ", cleaned).strip()
    expansions = _VENDOR_EXPANSIONS if entity_type == "vendor" else _MATERIAL_EXPANSIONS
    for pattern, replacement in expansions:
        cleaned = pattern.sub(replacement, cleaned)
    return _SPACE.sub(" ", cleaned).strip()


def spec_tokens(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _SPEC.finditer(text):
        token = re.sub(r"\s+", "", match.group(0).lower())
        if token and token not in seen:
            seen.add(token)
            found.append(token)
    return found
