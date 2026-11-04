from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import get_settings
from db import get_collection
from entities import entity_spec
from jev_client import JevError, judge_candidates
from normalize import lexical_query, normalize_query
from retrieve import retrieve

app = FastAPI(title="PCollab hybrid match")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MatchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    entityType: Literal["vendor", "material"]
    orgId: str = Field(..., min_length=1, max_length=80)
    orgOpuId: str = Field(default="", max_length=80)


class CandidateOut(BaseModel):
    id: str
    optionId: str | None
    rank: int
    label: str
    detail: str
    sources: list[str]
    lexicalRank: int | None
    vectorRank: int | None
    lexicalScore: float | None
    vectorScore: float | None
    fusedScore: float
    vectorFields: list[str]
    specTokens: list[str]
    missingQuerySpecs: list[str]
    sentToJev: bool


class JevOptionOut(BaseModel):
    optionId: str
    label: str
    probability: float
    candidateId: str | None


class JevOut(BaseModel):
    model: str | None = None
    choice: str | None = None
    choiceLabel: str | None = None
    confidence: float | None = None
    accepted: bool = False
    selectedCandidateId: str | None = None
    probabilities: list[JevOptionOut] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    error: str | None = None


class RetrievalError(BaseModel):
    source: str
    message: str


class MatchResponse(BaseModel):
    query: str
    luceneQuery: str
    vectorQuery: str
    normalizedQuery: str
    entityType: str
    collectionName: str
    luceneIndex: str
    vectorIndex: str
    candidateLimit: int
    confidenceThreshold: float
    candidates: list[CandidateOut]
    luceneCandidates: list[CandidateOut]
    vectorCandidates: list[CandidateOut]
    jev: JevOut
    retrievalErrors: list[RetrievalError]
    timingMs: dict[str, int]


def _public_candidate(item: dict[str, Any]) -> CandidateOut:
    payload = {key: value for key, value in item.items() if key != "jevText"}
    return CandidateOut(**payload)


def _judge(
    entity_type: str,
    query: str,
    normalized: str,
    candidates: list[dict[str, Any]],
) -> JevOut:
    current = get_settings()
    shortlist = [item for item in candidates if item["sentToJev"]]
    if not shortlist:
        return JevOut()
    try:
        judged = judge_candidates(
            api_key=current.typesafe_key,
            model=current.jev_model,
            entity_type=entity_type,
            query=query,
            normalized_query=normalized,
            options=[
                {"optionId": item["optionId"], "text": item["jevText"]} for item in shortlist
            ],
            timeout_seconds=current.jev_timeout_seconds,
        )
    except JevError as exc:
        return JevOut(error=str(exc))

    by_option = {item["optionId"]: item for item in shortlist}
    probabilities: list[JevOptionOut] = []
    raw_probabilities = judged["probabilities"]
    for option_id, item in by_option.items():
        probabilities.append(
            JevOptionOut(
                optionId=option_id,
                label=item["label"],
                probability=float(raw_probabilities.get(option_id, 0) or 0),
                candidateId=item["id"],
            )
        )
    no_match_probability = float(raw_probabilities.get("no_match", 0) or 0)
    probabilities.append(
        JevOptionOut(
            optionId="no_match",
            label="No match",
            probability=no_match_probability,
            candidateId=None,
        )
    )
    probabilities.sort(key=lambda option: option.probability, reverse=True)

    choice = str(judged["choice"])
    confidence = judged["confidence"]
    confidence_value = float(confidence) if isinstance(confidence, (int, float)) else None
    selected = by_option.get(choice)
    accepted = (
        selected is not None
        and confidence_value is not None
        and confidence_value >= current.jev_confidence_threshold
    )
    if choice == "no_match":
        choice_label = "No match"
    elif selected is not None:
        choice_label = selected["label"]
    else:
        choice_label = choice
    return JevOut(
        model=judged["model"],
        choice=choice,
        choiceLabel=choice_label,
        confidence=confidence_value,
        accepted=accepted,
        selectedCandidateId=selected["id"] if selected else None,
        probabilities=probabilities,
        usage=judged["usage"],
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def app_config():
    current = get_settings()
    entities = []
    for entity_type in ("vendor", "material"):
        spec = entity_spec(entity_type, current)
        entities.append(
            {
                "id": spec.id,
                "label": spec.label,
                "collectionName": spec.collection,
                "luceneIndex": spec.lucene_index,
                "vectorIndex": spec.vector_index,
                "requiresOrgOpuId": spec.requires_org_opu_id,
                "vectorFields": list(spec.vector_paths),
            }
        )
    return {
        "entities": entities,
        "jevModel": current.jev_model,
        "confidenceThreshold": current.jev_confidence_threshold,
        "jevCandidateLimit": current.jev_candidate_limit,
    }


@app.post("/match", response_model=MatchResponse)
def match(body: MatchRequest):
    current = get_settings()
    spec = entity_spec(body.entityType, current)
    org_opu_id = body.orgOpuId.strip()
    if spec.requires_org_opu_id and not org_opu_id:
        raise HTTPException(status_code=400, detail="orgOpuId is required for material search")

    query = body.query.strip()
    lucene_name_query = lexical_query(query, spec.id) or query
    vector_query = normalize_query(query, spec.id) or query
    print(
        "\n".join(
            [
                f"[match] entity={spec.id}",
                f"[match] user query     = {query!r}",
                f"[match] lucene name    = {lucene_name_query!r}"
                + (
                    " (codes still use the raw user query)"
                    if lucene_name_query != query
                    else ""
                ),
                f"[match] vector query   = {vector_query!r}",
                f"[match] lucene index   = {spec.lucene_index}",
                f"[match] vector index   = {spec.vector_index}",
                f"[match] vector numCandidates = {current.vector_num_candidates}"
                f" (return limit {current.vector_limit})",
            ]
        ),
        flush=True,
    )
    started = time.perf_counter()
    candidates, lucene_candidates, vector_candidates, errors, timing = retrieve(
        get_collection(spec.collection),
        spec,
        query,
        vector_query,
        body.orgId.strip(),
        org_opu_id,
        current.lexical_limit,
        current.vector_limit,
        current.vector_num_candidates,
        current.hybrid_result_limit,
        current.jev_candidate_limit,
    )
    if not candidates and errors:
        lexical_failed = any(error["source"] == "lexical" for error in errors)
        vector_failed = any(error["source"] != "lexical" for error in errors)
        if lexical_failed and vector_failed:
            detail = "; ".join(f"{error['source']}: {error['message']}" for error in errors)
            raise HTTPException(status_code=502, detail=detail)

    jev_started = time.perf_counter()
    jev = _judge(spec.id, query, vector_query, candidates)
    timing["jev"] = int((time.perf_counter() - jev_started) * 1000)
    timing["total"] = int((time.perf_counter() - started) * 1000)
    print(
        f"[match] hits lucene={len(lucene_candidates)} "
        f"vector={len(vector_candidates)} fused={len(candidates)} "
        f"errors={len(errors)} timing={timing}",
        flush=True,
    )
    return MatchResponse(
        query=query,
        luceneQuery=lucene_name_query,
        vectorQuery=vector_query,
        normalizedQuery=vector_query,
        entityType=spec.id,
        collectionName=spec.collection,
        luceneIndex=spec.lucene_index,
        vectorIndex=spec.vector_index,
        candidateLimit=current.jev_candidate_limit,
        confidenceThreshold=current.jev_confidence_threshold,
        candidates=[_public_candidate(item) for item in candidates],
        luceneCandidates=[_public_candidate(item) for item in lucene_candidates],
        vectorCandidates=[_public_candidate(item) for item in vector_candidates],
        jev=jev,
        retrievalErrors=[RetrievalError(**error) for error in errors],
        timingMs=timing,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
