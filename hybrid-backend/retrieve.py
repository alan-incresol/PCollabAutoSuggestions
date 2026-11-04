from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from entities import EntitySpec
from normalize import lexical_query, spec_tokens

RRF_K = 60
_INDEX_CACHE_SECONDS = 30.0
_INDEX_CACHE: dict[str, tuple[float, str | None]] = {}

VECTOR_FIELD_LABELS = {
    "vendorDetails.basicDetails.companyName": "company name",
    "materialData.materialDetails.discription": "description",
}


@dataclass
class Hit:
    doc_id: str
    score: float
    doc: dict[str, Any]
    vector_fields: set[str] = field(default_factory=set)


def collect_strings(node: Any, parts: list[str]) -> list[str]:
    if not parts:
        if isinstance(node, str):
            text = node.strip()
            return [text] if text else []
        if isinstance(node, bool) or node is None:
            return []
        if isinstance(node, (int, float)):
            return [str(node)]
        return []
    if isinstance(node, dict):
        child = node.get(parts[0])
        if child is None:
            return []
        return collect_strings(child, parts[1:])
    if isinstance(node, list):
        values: list[str] = []
        for item in node:
            values.extend(collect_strings(item, parts))
        return values
    return []


def first_text(doc: dict[str, Any], path: str, limit: int = 240) -> str:
    values = collect_strings(doc, path.split("."))
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            unique.append(value)
    text = " · ".join(unique[:3])
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def describe(spec: EntitySpec, doc: dict[str, Any]) -> tuple[str, str]:
    label = first_text(doc, spec.label_path, limit=180) or "(no name)"
    details: list[str] = []
    for caption, path in spec.detail_paths:
        value = first_text(doc, path, limit=280)
        if value and value.lower() != label.lower():
            details.append(f"{caption}: {value}")
    return label, " · ".join(details)


def lexical_pipeline(
    spec: EntitySpec,
    query: str,
    org_id: str,
    org_opu_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = [
        {"equals": {"path": "markAsDelete", "value": False}},
        {"text": {"query": org_id, "path": "orgId"}},
    ]
    if spec.requires_org_opu_id:
        filters.append({"text": {"query": org_opu_id, "path": "orgOpuId"}})
    name_query = lexical_query(query, spec.id)
    should: list[dict[str, Any]] = []
    for path, fuzzy in spec.lexical_paths:
        clause: dict[str, Any] = {
            "query": name_query if fuzzy else query,
            "path": path,
            "tokenOrder": "any",
        }
        if fuzzy:
            clause["fuzzy"] = {"maxEdits": 1, "prefixLength": 1, "maxExpansions": 50}
        should.append({"autocomplete": clause})
    return [
        {
            "$search": {
                "index": spec.lucene_index,
                "compound": {
                    "filter": filters,
                    "should": should,
                    "minimumShouldMatch": 1,
                },
            }
        },
        {"$addFields": {"score": {"$meta": "searchScore"}}},
        {"$limit": limit},
        {"$project": {**spec.projection, "score": 1}},
    ]


def vector_pipeline(
    spec: EntitySpec,
    path: str,
    query: str,
    org_id: str,
    org_opu_id: str,
    limit: int,
    num_candidates: int,
) -> list[dict[str, Any]]:
    prefilter: dict[str, Any] = {"orgId": org_id, "markAsDelete": False}
    if spec.requires_org_opu_id:
        prefilter["orgOpuId"] = org_opu_id
    return [
        {
            "$vectorSearch": {
                "index": spec.vector_index,
                "path": path,
                "query": {"text": query},
                "limit": limit,
                "numCandidates": max(num_candidates, limit),
                "filter": prefilter,
            }
        },
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        {"$limit": limit},
        {"$project": {**spec.projection, "score": 1}},
    ]


def _hit_from_doc(doc: dict[str, Any], vector_field: str | None = None) -> Hit:
    score = float(doc.pop("score", 0) or 0)
    doc_id = str(doc.pop("_id"))
    fields = {vector_field} if vector_field else set()
    return Hit(doc_id=doc_id, score=score, doc=doc, vector_fields=fields)


def run_lexical(collection: Any, pipeline: list[dict[str, Any]]) -> list[Hit]:
    return [_hit_from_doc(doc) for doc in collection.aggregate(pipeline)]


def vector_index_issue(collection: Any, index_name: str) -> str | None:
    cache_key = f"{collection.full_name}:{index_name}"
    cached = _INDEX_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < _INDEX_CACHE_SECONDS:
        return cached[1]
    try:
        indexes = list(collection.list_search_indexes())
    except Exception:
        return None
    match = next((index for index in indexes if index.get("name") == index_name), None)
    if match is None:
        issue = (
            f"Vector index '{index_name}' is not on this collection yet. "
            "Create it in Atlas with the JSON in hybrid-backend/indexes and wait until it is queryable."
        )
    else:
        status = str(match.get("status") or "PENDING")
        issue = (
            None
            if match.get("queryable") is not False and status.upper() in {"READY", "STEADY"}
            else f"Vector index '{index_name}' is {status} and is not queryable yet."
        )
    _INDEX_CACHE[cache_key] = (now, issue)
    return issue


def run_vector(collection: Any, pipeline: list[dict[str, Any]], path: str) -> list[Hit]:
    return [_hit_from_doc(doc, path) for doc in collection.aggregate(pipeline)]


def merge_vector_hits(groups: list[list[Hit]]) -> list[Hit]:
    merged: dict[str, Hit] = {}
    for group in groups:
        for hit in group:
            current = merged.get(hit.doc_id)
            if current is None or hit.score > current.score:
                hit.vector_fields = set(hit.vector_fields)
                if current is not None:
                    hit.vector_fields |= current.vector_fields
                merged[hit.doc_id] = hit
            else:
                current.vector_fields |= hit.vector_fields
    ranked = sorted(merged.values(), key=lambda hit: hit.score, reverse=True)
    return ranked


def fuse(
    lexical: list[Hit],
    vector: list[Hit],
    query: str,
    spec: EntitySpec,
) -> list[dict[str, Any]]:
    query_specs = spec_tokens(query) if spec.id == "material" else []
    lexical_rank = {hit.doc_id: index for index, hit in enumerate(lexical, start=1)}
    vector_rank = {hit.doc_id: index for index, hit in enumerate(vector, start=1)}
    docs: dict[str, Hit] = {}
    for hit in lexical + vector:
        docs.setdefault(hit.doc_id, hit)
    vector_fields = {hit.doc_id: set(hit.vector_fields) for hit in vector}
    lexical_scores = {hit.doc_id: hit.score for hit in lexical}
    vector_scores = {hit.doc_id: hit.score for hit in vector}

    fused: list[dict[str, Any]] = []
    for doc_id, hit in docs.items():
        score = 0.0
        lex_rank = lexical_rank.get(doc_id)
        vec_rank = vector_rank.get(doc_id)
        if lex_rank is not None:
            score += 1.0 / (RRF_K + lex_rank)
        if vec_rank is not None:
            score += 1.0 / (RRF_K + vec_rank)
        label, detail = describe(spec, hit.doc)
        blob = f"{label} {detail}"
        present = spec_tokens(blob)
        missing = [token for token in query_specs if token not in present]
        sources: list[str] = []
        if lex_rank is not None:
            sources.append("lexical")
        if vec_rank is not None:
            sources.append("vector")
        fused.append(
            {
                "id": doc_id,
                "label": label,
                "detail": detail,
                "sources": sources,
                "lexicalRank": lex_rank,
                "vectorRank": vec_rank,
                "lexicalScore": lexical_scores.get(doc_id),
                "vectorScore": vector_scores.get(doc_id),
                "fusedScore": score,
                "vectorFields": sorted(
                    VECTOR_FIELD_LABELS.get(path, path) for path in vector_fields.get(doc_id, set())
                ),
                "specTokens": present,
                "missingQuerySpecs": missing,
                "jevText": _jev_text(label, detail, present),
            }
        )
    fused.sort(key=lambda item: (-item["fusedScore"], item["label"].lower()))
    return fused


def _jev_text(label: str, detail: str, specs: list[str]) -> str:
    text = label if not detail else f"{label} | {detail}"
    if specs:
        text = f"{text} | spec tokens: {', '.join(specs[:12])}"
    return text[:700]


def retrieve(
    collection: Any,
    spec: EntitySpec,
    query: str,
    vector_query: str,
    org_id: str,
    org_opu_id: str,
    lexical_limit: int,
    vector_limit: int,
    num_candidates: int,
    result_limit: int,
    jev_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]], dict[str, int]]:
    errors: list[dict[str, str]] = []
    timing: dict[str, int] = {}

    def _lexical() -> tuple[list[Hit], int, str | None]:
        started = time.perf_counter()
        try:
            hits = run_lexical(
                collection,
                lexical_pipeline(spec, query, org_id, org_opu_id, lexical_limit),
            )
            return hits, int((time.perf_counter() - started) * 1000), None
        except Exception as exc:
            return [], int((time.perf_counter() - started) * 1000), str(exc)[:500]

    def _vector(path: str) -> tuple[str, list[Hit], int, str | None]:
        started = time.perf_counter()
        try:
            hits = run_vector(
                collection,
                vector_pipeline(
                    spec, path, vector_query, org_id, org_opu_id, vector_limit, num_candidates
                ),
                path,
            )
            return path, hits, int((time.perf_counter() - started) * 1000), None
        except Exception as exc:
            return path, [], int((time.perf_counter() - started) * 1000), str(exc)[:500]

    lexical_hits: list[Hit] = []
    vector_groups: list[list[Hit]] = []
    index_issue = vector_index_issue(collection, spec.vector_index)
    vector_paths = () if index_issue else spec.vector_paths
    if index_issue:
        errors.append({"source": "vector", "message": index_issue})
        timing["vector"] = 0
    workers = max(1, 1 + len(vector_paths))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        lexical_future = pool.submit(_lexical)
        vector_futures = [pool.submit(_vector, path) for path in vector_paths]
        lexical_hits, timing["lexical"], lexical_error = lexical_future.result()
        if lexical_error:
            errors.append({"source": "lexical", "message": lexical_error})
        vector_ms = 0
        for future in vector_futures:
            path, hits, elapsed, vector_error = future.result()
            vector_ms = max(vector_ms, elapsed)
            if vector_error:
                errors.append(
                    {
                        "source": VECTOR_FIELD_LABELS.get(path, path),
                        "message": vector_error,
                    }
                )
            elif hits:
                vector_groups.append(hits)
        timing["vector"] = vector_ms

    vector_hits = merge_vector_hits(vector_groups)
    ranked = fuse(lexical_hits, vector_hits, query, spec)
    shortlist_cutoff = min(result_limit, jev_limit)
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
        item["sentToJev"] = rank <= shortlist_cutoff
        item["optionId"] = f"c{rank}" if item["sentToJev"] else None
    lucene = sorted(
        (item for item in ranked if item["lexicalRank"] is not None),
        key=lambda item: item["lexicalRank"],
    )
    vector = sorted(
        (item for item in ranked if item["vectorRank"] is not None),
        key=lambda item: item["vectorRank"],
    )
    return ranked[:result_limit], lucene, vector, errors, timing
