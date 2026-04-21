from typing import Any

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import settings
from db import get_collection

FIELD_PATHS: dict[str, str] = {
    "city": "vendorDetails.vendorAddressDetails.city",
    "gstin": "vendorDetails.companyOverviewDetails.gstin",
    "pointOfContactName": "vendorDetails.basicDetails.pointOfContactName",
    "contactEmail": "vendorDetails.basicDetails.contactEmail",
    "vendorCode": "vendorCode",
    "erpSyncMsg": "erpSyncMsg",
    "companyName" :"vendorDetails.basicDetails.companyName"
}

ALLOWED_FIELDS = frozenset(FIELD_PATHS.keys())

app = FastAPI(title="Vendor Atlas Search API")

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


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    fields: list[str] = Field(..., min_length=1)


class SuggestRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    fields: list[str] = Field(..., min_length=1)


class SuggestResponse(BaseModel):
    suggestions: list[str]


class SearchResponse(BaseModel):
    count: int
    documents: list[dict[str, Any]]


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


def build_search_stage(query: str, fields: list[str]) -> dict[str, Any]:
    paths = [FIELD_PATHS[f] for f in fields]
    if len(paths) == 1:
        return {
            "$search": {
                "index": settings.search_index_name,
                "autocomplete": {"query": query, "path": paths[0]},
            }
        }
    return {
        "$search": {
            "index": settings.search_index_name,
            "compound": {
                "should": [
                    {"autocomplete": {"query": query, "path": p}} for p in paths
                ],
                "minimumShouldMatch": 1,
            },
        }
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/suggest", response_model=SuggestResponse)
def suggest(body: SuggestRequest):
    unknown = [f for f in body.fields if f not in ALLOWED_FIELDS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fields: {unknown}. Allowed: {sorted(ALLOWED_FIELDS)}",
        )

    coll = get_collection()
    pipeline: list[dict[str, Any]] = [
        build_search_stage(body.query.strip(), body.fields),
        {"$limit": settings.search_result_limit},
    ]

    try:
        cursor = coll.aggregate(pipeline)
        seen: set[str] = set()
        q_lower = body.query.strip().lower()
        for doc in cursor:
            for field_key in body.fields:
                path_parts = FIELD_PATHS[field_key].split(".")
                for val in _get_nested_values(doc, path_parts):
                    stripped = val.strip()
                    if stripped and q_lower in stripped.lower():
                        seen.add(stripped)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Suggest failed: {e!s}") from e

    # Deduplicate case-insensitively, keeping the first-seen casing
    unique: dict[str, str] = {}
    for v in sorted(seen):
        key = v.lower()
        if key not in unique:
            unique[key] = v
    return SuggestResponse(suggestions=sorted(unique.values(), key=str.lower))


@app.post("/search", response_model=SearchResponse)
def search(body: SearchRequest):
    unknown = [f for f in body.fields if f not in ALLOWED_FIELDS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fields: {unknown}. Allowed: {sorted(ALLOWED_FIELDS)}",
        )

    coll = get_collection()
    pipeline: list[dict[str, Any]] = [
        build_search_stage(body.query.strip(), body.fields),
        {"$limit": settings.search_result_limit},
    ]

    try:
        cursor = coll.aggregate(pipeline)
        docs = [serialize_doc(d) for d in cursor]
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Search failed: {e!s}",
        ) from e

    return SearchResponse(count=len(docs), documents=docs)


if __name__=='__main__':
    import uvicorn
    uvicorn.run("main:app",port =5000)