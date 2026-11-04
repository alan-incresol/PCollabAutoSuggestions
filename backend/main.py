from dataclasses import dataclass
from typing import Any

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import ENV_FILE, get_settings, settings
from correction import MIN_QUERY_LENGTH, correct_query
from db import get_collection
from search_registry import (
    COLLECTION_REGISTRY,
    field_label,
    get_collection_config,
    list_known_collections,
    resolve_collection_name,
)

app = FastAPI(title="PR Atlas Search API")

_boot = get_settings()
print(
    f"Settings file: {ENV_FILE} "
    f"(exists={ENV_FILE.is_file()}) "
    f"db={_boot.mongodb_db} collection={_boot.collection_name} "
    f"index={_boot.search_index_name}"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def serialize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, dict):
            out[k] = serialize_doc(v)
        elif isinstance(v, list):
            out[k] = [
                serialize_doc(i) if isinstance(i, dict) else (str(i) if isinstance(i, ObjectId) else i)
                for i in v
            ]
        else:
            out[k] = v
    return out


class SuggestRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    fields: list[str] = Field(
        default_factory=list,
        description="Field ids to search; empty searches all indexed fields.",
    )
    orgId: str = Field(..., min_length=1)
    orgOpuId: str = Field(default="")
    collectionName: str | None = Field(
        default=None,
        description="MongoDB collection; default from COLLECTION_NAME env.",
    )
    searchIndexName: str | None = Field(
        default=None,
        description="Override Atlas index name from the built-in registry.",
    )


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    fields: list[str] = Field(
        default_factory=list,
        description="Field ids to search; empty searches all indexed fields.",
    )
    orgId: str = Field(..., min_length=1)
    orgOpuId: str = Field(default="")
    collectionName: str | None = Field(default=None)
    searchIndexName: str | None = Field(default=None)


class SuggestResponse(BaseModel):
    suggestions: list[str]


class SearchResponse(BaseModel):
    count: int
    documents: list[dict[str, Any]]


class FieldConfig(BaseModel):
    id: str
    label: str
    path: str


class AppConfigResponse(BaseModel):
    collectionName: str
    searchIndexName: str
    requiresOrgOpuId: bool
    fields: list[FieldConfig]


def _resolve_target(
    collection_name: str | None, index_override: str | None
) -> tuple[str, str, dict[str, str], bool]:
    raw = collection_name or get_settings().collection_name
    try:
        coll = resolve_collection_name(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    config = COLLECTION_REGISTRY[coll]
    index_name = (index_override or config.index_name).strip()
    return coll, index_name, config.field_paths, config.requires_org_opu_id


def _get_nested_values(doc: Any, parts: list[str]) -> list[str]:
    """Walk a dotted path, expanding through arrays, and collect all leaf string values."""
    if not parts:
        return [doc] if isinstance(doc, str) else []
    key, rest = parts[0], parts[1:]
    if isinstance(doc, dict):
        child = doc.get(key)
        if child is None:
            return []
        return _get_nested_values(child, rest)
    if isinstance(doc, list):
        results: list[str] = []
        for item in doc:
            results.extend(_get_nested_values(item, [key] + rest))
        return results
    return []


def _resolve_fields(fields: list[str], field_paths: dict[str, str]) -> list[str]:
    if fields:
        return fields
    return list(field_paths.keys())


def build_search_stage(
    query: str,
    fields: list[str],
    org_id: str,
    org_opu_id: str,
    index_name: str,
    field_paths: dict[str, str],
    requires_org_opu_id: bool,
    fuzzy: bool = False,
) -> dict[str, Any]:
    search_paths: list[str] = []
    seen_paths: set[str] = set()
    for field_key in fields:
        path = field_paths[field_key]
        if path not in seen_paths:
            seen_paths.add(path)
            search_paths.append(path)
    filters: list[dict[str, Any]] = [
        {"equals": {"path": "markAsDelete", "value": False}},
        {"text": {"query": org_id, "path": "orgId"}},
    ]
    if requires_org_opu_id:
        filters.append({"text": {"query": org_opu_id, "path": "orgOpuId"}})
    # Fuzzy matching is a query option, so the existing autocomplete index serves it unchanged.
    extra: dict[str, Any] = {"fuzzy": {"maxEdits": 2}} if fuzzy else {}
    return {
        "$search": {
            "index": index_name,
            "compound": {
                "filter": filters,
                "should": [
                    {"autocomplete": {"query": query, "path": p, **extra}} for p in search_paths
                ],
                "minimumShouldMatch": 1,
            },
        }
    }


def _validate_org_filters(org_opu_id: str, requires_org_opu_id: bool) -> None:
    if requires_org_opu_id and not org_opu_id.strip():
        raise HTTPException(status_code=400, detail="orgOpuId is required for this collection")


@dataclass(frozen=True)
class _Target:
    coll_name: str
    index_name: str
    field_paths: dict[str, str]
    requires_org_opu_id: bool
    org_id: str
    org_opu_id: str

    def run(self, query: str, fields: list[str], *, fuzzy: bool = False) -> list[dict[str, Any]]:
        pipeline: list[dict[str, Any]] = [
            build_search_stage(
                query,
                fields,
                self.org_id,
                self.org_opu_id,
                self.index_name,
                self.field_paths,
                self.requires_org_opu_id,
                fuzzy=fuzzy,
            ),
            {"$limit": get_settings().search_result_limit},
        ]
        return list(get_collection(self.coll_name).aggregate(pipeline))


def _distinct_values(
    docs: list[dict[str, Any]], fields: list[str], field_paths: dict[str, str]
) -> list[str]:
    """Unique non-empty string values of `fields` across `docs`, in result (relevance) order."""
    seen: dict[str, str] = {}
    for doc in docs:
        for field_key in fields:
            for val in _get_nested_values(doc, field_paths[field_key].split(".")):
                stripped = val.strip()
                if stripped and stripped.lower() not in seen:
                    seen[stripped.lower()] = stripped
    return list(seen.values())


def _search_with_correction(
    target: _Target, query: str, search_fields: list[str]
) -> tuple[str, list[dict[str, Any]]]:
    """Search with Jev's spelling correction on correctable fields; fall back to the text as typed.

    Returns the query that produced the documents along with them.
    """
    correctable_ids = COLLECTION_REGISTRY[target.coll_name].correctable_fields
    correctable = [f for f in search_fields if f in correctable_ids]
    if correctable and len(query) >= MIN_QUERY_LENGTH:
        nearby = target.run(query, correctable, fuzzy=True)
        candidates = _distinct_values(nearby, correctable, target.field_paths)
        corrected = correct_query(query, candidates, field_label(correctable[0]))
        if corrected:
            docs = target.run(corrected, search_fields)
            if docs:
                return corrected, docs
    return query, target.run(query, search_fields)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config", response_model=AppConfigResponse)
def app_config():
    config = get_collection_config(get_settings().collection_name)
    return AppConfigResponse(**config)


@app.post("/suggest", response_model=SuggestResponse)
def suggest(body: SuggestRequest):
    coll_name, index_name, field_paths, requires_org_opu_id = _resolve_target(
        body.collectionName, body.searchIndexName
    )
    _validate_org_filters(body.orgOpuId, requires_org_opu_id)
    search_fields = _resolve_fields(body.fields, field_paths)
    allowed = frozenset(field_paths.keys())
    unknown = [f for f in search_fields if f not in allowed]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fields: {unknown}. Allowed for {coll_name}: {sorted(allowed)}",
        )

    target = _Target(
        coll_name, index_name, field_paths, requires_org_opu_id, body.orgId, body.orgOpuId
    )

    try:
        effective_query, docs = _search_with_correction(target, body.query.strip(), search_fields)
        seen: set[str] = set()
        q_lower = effective_query.lower()
        for doc in docs:
            for field_key in search_fields:
                path_parts = field_paths[field_key].split(".")
                for val in _get_nested_values(doc, path_parts):
                    stripped = val.strip()
                    if stripped and q_lower in stripped.lower():
                        seen.add(stripped)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Suggest failed: {e!s}") from e

    unique: dict[str, str] = {}
    for v in sorted(seen):
        key = v.lower()
        if key not in unique:
            unique[key] = v
    return SuggestResponse(suggestions=sorted(unique.values(), key=str.lower))


@app.post("/search", response_model=SearchResponse)
def search(body: SearchRequest):
    coll_name, index_name, field_paths, requires_org_opu_id = _resolve_target(
        body.collectionName, body.searchIndexName
    )
    _validate_org_filters(body.orgOpuId, requires_org_opu_id)
    search_fields = _resolve_fields(body.fields, field_paths)
    allowed = frozenset(field_paths.keys())
    unknown = [f for f in search_fields if f not in allowed]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fields: {unknown}. Allowed for {coll_name}: {sorted(allowed)}",
        )

    target = _Target(
        coll_name, index_name, field_paths, requires_org_opu_id, body.orgId, body.orgOpuId
    )

    try:
        _, found = _search_with_correction(target, body.query.strip(), search_fields)
        docs = [serialize_doc(d) for d in found]
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Search failed: {e!s}",
        ) from e

    return SearchResponse(count=len(docs), documents=docs)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=5000,reload=True,host="0.0.0.0")
