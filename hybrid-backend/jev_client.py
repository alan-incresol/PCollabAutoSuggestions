from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"

_INSTRUCTIONS = {
    "vendor": (
        "Which candidate is the same company as the user query? "
        "Treat private/pvt, limited/ltd, corporation/corp, company/co, and engg/engineering as the same. "
        "Ignore letter case and minor spelling differences. "
        "Select no_match when none of the candidates is that company."
    ),
    "material": (
        "Which candidate is the same material as the user query? "
        "Wording, abbreviations, and small typos may differ. "
        "A different size, length, gauge, diameter, colour, or part number is a different material. "
        "Select no_match when none of the candidates is that material."
    ),
}


class JevError(Exception):
    pass


def judge_candidates(
    *,
    api_key: str,
    model: str,
    entity_type: str,
    query: str,
    normalized_query: str,
    options: list[dict[str, str]],
    timeout_seconds: float,
) -> dict[str, Any]:
    if not api_key:
        raise JevError("TYPESAFE_API_KEY is empty")
    criteria = {option["optionId"]: option["text"] for option in options}
    criteria["no_match"] = (
        "None of the candidates is the same "
        + ("company" if entity_type == "vendor" else "material")
    )
    body = {
        "model": model,
        "state": {
            "entity_type": entity_type,
            "user_query": query,
            "normalized_query": normalized_query,
            "candidates": [
                {"id": option["optionId"], "text": option["text"]} for option in options
            ],
        },
        "questions": {
            "best_match": {
                "type": "choice",
                "instructions": _INSTRUCTIONS[entity_type],
                "criteria": criteria,
            }
        },
    }
    request = urllib.request.Request(
        TYPESAFE_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:2000]
        raise JevError(f"Decision service HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise JevError(f"Decision request failed: {exc.reason}") from exc

    answer = payload.get("answers", {}).get("best_match")
    if not isinstance(answer, dict) or "choice" not in answer:
        raise JevError("Decision response did not include a choice")
    return {
        "model": payload.get("model") or model,
        "choice": answer.get("choice"),
        "confidence": answer.get("confidence"),
        "probabilities": answer.get("probabilities") or {},
        "usage": payload.get("usage"),
    }
