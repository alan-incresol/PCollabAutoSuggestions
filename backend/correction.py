"""
Spell-correct search text with TypeSafe AI's Jev model before it reaches Atlas Search.

Jev answers classification questions rather than generating text, so correction is a
`Choice` between real values already in the collection (found by a fuzzy Atlas Search in
main.py) plus an option to keep the text as typed.
"""

from __future__ import annotations

import logging

from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

from config import get_settings

logger = logging.getLogger(__name__)

KEEP_ORIGINAL = "KEEP_ORIGINAL"
MIN_QUERY_LENGTH = 3
MAX_CANDIDATES = 15

_client: TypeSafeClient | None = None
_client_key: tuple[str, float] | None = None


def get_client() -> TypeSafeClient | None:
    """Shared Jev client, rebuilt when the key or timeout in backend/.env changes; None when unconfigured."""
    global _client, _client_key
    settings = get_settings()
    api_key = settings.typesafe_api_key.get_secret_value().strip()
    if not api_key:
        return None
    key = (api_key, settings.correction_timeout_seconds)
    if _client is None or _client_key != key:
        if _client is not None:
            _client.close()
            _client = None
        timeout = settings.correction_timeout_seconds
        try:
            _client = TypeSafeClient(
                api_key=api_key,
                model=settings.typesafe_model,
                timeout=timeout,
                retry=RetryPolicy(max_retries=1, timeout=timeout),
            )
        except Exception as e:
            logger.warning("Jev client unavailable (%s); correction disabled", type(e).__name__)
            return None
        _client_key = key
    return _client


def correct_query(query: str, candidates: list[str], subject: str) -> str | None:
    """Return the candidate Jev picks as the intended text, or None to search the text as typed.

    `subject` names what is being searched (e.g. "Company Name") for the model's instructions.
    """
    q = query.strip()
    if len(q) < MIN_QUERY_LENGTH or not candidates:
        return None
    q_lower = q.lower()
    # The typed text already appears in real values, so the normal search will find them.
    if any(q_lower in c.lower() for c in candidates):
        return None

    client = get_client()
    if client is None:
        return None

    options = candidates[:MAX_CANDIDATES]
    criteria: dict[str, str | None] = {c: None for c in options}
    criteria[KEEP_ORIGINAL] = (
        "None of the listed values is what the user meant, or there is not enough "
        "evidence to pick one."
    )
    try:
        response = client.system_one(
            state={"typed_text": q, "searching": subject},
            questions={
                "intended": Choice(
                    instructions=(
                        f"A user typed this into a {subject} search box. It may be misspelled, "
                        "mistyped, or use different spacing or punctuation. Which listed value "
                        "did they most likely mean?"
                    ),
                    criteria=criteria,
                )
            },
        )
        answer = response.choices["intended"]
    except Exception as e:
        # Best effort: any SDK, network, timeout, or response-shape failure means search as typed.
        logger.warning("Jev correction failed (%s); searching original text", type(e).__name__)
        return None

    if answer.choice not in options:
        return None
    if answer.confidence < get_settings().correction_min_confidence:
        return None
    return answer.choice
