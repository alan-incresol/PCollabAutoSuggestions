# Hybrid retrieval (before Jev)

This document describes how `POST /match` builds the candidate shortlist **before** the decision model runs. Implementation lives mainly in `normalize.py`, `entities.py`, and `retrieve.py`.

The decision layer is out of scope here. It only receives the top fused candidates already ranked by this pipeline.

## End-to-end flow

```text
User query + entityType (vendor | material) + orgId [+ orgOpuId]
        │
        ├─► lexical_query(query)     ── used by Lucene on name/description fields
        └─► normalize_query(query)   ── used as Voyage embedding query text
        │
        ▼
   Parallel retrieval
        ├─► Atlas Search ($search) on Lucene index     → up to LEXICAL_LIMIT hits
        └─► Atlas Vector Search ($vectorSearch)        → up to VECTOR_LIMIT hits
        │
        ▼
   Fuse with Reciprocal Rank Fusion (RRF)
        │
        ▼
   Attach material spec-token annotations (informational)
        │
        ▼
   Keep top HYBRID_RESULT_LIMIT · mark top JEV_CANDIDATE_LIMIT for Jev
```

Default limits (from `.env`):

| Setting | Default | Role |
| --- | --- | --- |
| `LEXICAL_LIMIT` | 20 | Max Lucene hits |
| `VECTOR_LIMIT` | 20 | Max vector hits returned |
| `VECTOR_NUM_CANDIDATES` | 200 | ANN over-request size inside Atlas (`numCandidates`). MongoDB recommends about **20×** `VECTOR_LIMIT` for recall. With limit 20, 200 is that default. Lower values (e.g. 80–100) are faster but can miss near neighbors; this does not change Voyage embedding cost, only the ANN search work. |
| `HYBRID_RESULT_LIMIT` | 15 | Max fused candidates returned to the UI |
| `JEV_CANDIDATE_LIMIT` | 10 | How many of those fused rows are sent to Jev |

Both legs always filter `markAsDelete = false` and `orgId`. Materials also filter `orgOpuId`. Vendors do not filter on `orgOpuId`.

---

## 1. Query preprocessing

Two different strings are derived from the raw user query.

### Lucene query (`lexical_query`)

- **Materials:** the raw query is used as typed (trimmed).
- **Vendors:** alphanumeric tokens are kept; legal/noise tokens are dropped:

  `pvt`, `ltd`, `limited`, `private`, `corp`, `corporation`, `co`, `company`, `llp`, `inc`, `ms`, `the`, `and`

  Example: `wipro ltd` → `wipro`

  That keeps Atlas autocomplete from ranking every company whose name ends in “Ltd”.

Codes (`vendorCode`, `erpVendorCode`, `material`) still search against the **raw** query, not the stripped name query.

### Vector query (`normalize_query`)

Used only for `$vectorSearch.query.text` so Voyage embeds a cleaned string:

1. Lowercase
2. Strip punctuation to spaces
3. Expand abbreviations:
   - Vendors: `pvt→private`, `ltd→limited`, `corp→corporation`, `engg→engineering`, `co→company`
   - Materials: `sch→schedule`, `dia→diameter`, `ss→stainless steel`, `ms→mild steel`, `nb→nominal bore`, `upvc`/`pvc` normalized

Example: `western engg pvt ltd` → `western engineering private limited`

---

## 2. Lucene / Atlas Search leg

Index names: `vendor-master` / `material-master`.

Stage shape:

```json
{
  "$search": {
    "index": "<lucene-index>",
    "compound": {
      "filter": [
        { "equals": { "path": "markAsDelete", "value": false } },
        { "text": { "query": "<orgId>", "path": "orgId" } }
        // + orgOpuId text filter for materials
      ],
      "should": [ /* autocomplete clauses */ ],
      "minimumShouldMatch": 1
    }
  }
}
```

### Fields searched

| Entity | Path | Fuzzy? | Query string used |
| --- | --- | --- | --- |
| Vendor | `vendorDetails.basicDetails.companyName` | yes (`maxEdits: 1`) | `lexical_query` |
| Vendor | `vendorCode` | no | raw query |
| Vendor | `erpVendorCode` | no | raw query |
| Material | `materialData.materialDetails.discription` | yes | raw query |
| Material | `material` | no | raw query |

All autocomplete clauses use `tokenOrder: "any"` so word order in the query does not have to match the stored name.

Fuzzy settings on name/description: `maxEdits: 1`, `prefixLength: 1`, `maxExpansions: 50`.

Atlas returns its own `searchScore`. Hits are kept in Atlas order as Lucene rank 1…N.

If Lucene fails, the error is recorded and this leg contributes no hits. Vector (if healthy) can still populate the fused list.

---

## 3. Vector / Voyage leg

Index names: `vendor-master-vector` / `material-master-vector` (`voyage-4` autoEmbed).

Before querying, the code checks that the vector index exists and is queryable. If not, vector is skipped and a retrieval warning is returned; Lucene still runs.

Stage shape:

```json
{
  "$vectorSearch": {
    "index": "<vector-index>",
    "path": "<embedded-field>",
    "query": { "text": "<normalize_query result>" },
    "filter": { "orgId": "...", "markAsDelete": false },
    "numCandidates": 200,
    "limit": 20
  }
}
```

### Embedded paths

| Entity | Path |
| --- | --- |
| Vendor | `vendorDetails.basicDetails.companyName` |
| Material | `materialData.materialDetails.discription` |

Atlas embeds the query text with the same Voyage model used at index time and ranks by vector similarity (`vectorSearchScore`).

`numCandidates` is the ANN candidate pool inside Atlas; `limit` is how many documents are returned to the app. Code uses `max(VECTOR_NUM_CANDIDATES, VECTOR_LIMIT)`.

If multiple vector paths ever exist, hits are merged by `_id`, keeping the highest vector score and unioning which fields matched. Today each entity has a single path.

---

## 4. Hybrid fusion (RRF) — the “rerank” before Jev

This is **not** a learned reranker. It is **Reciprocal Rank Fusion** over the two ranked lists.

Constant: `RRF_K = 60`.

For every distinct document id that appeared in Lucene and/or vector:

```text
fusedScore =
    (1 / (60 + luceneRank)   if present in Lucene else 0)
  + (1 / (60 + vectorRank)   if present in vector else 0)
```

Ranks are 1-based positions in each leg’s result list (not raw Atlas scores). Raw Lucene and vector scores are kept for display only; they are **not** mixed into `fusedScore`.

Then:

1. Sort by `fusedScore` descending, tie-break by label ascending.
2. Assign combined `rank` = 1…N.
3. Truncate to `HYBRID_RESULT_LIMIT` (default 15) for the Combined tab / API `candidates`.
4. Mark `sentToJev = true` for ranks `1 … min(HYBRID_RESULT_LIMIT, JEV_CANDIDATE_LIMIT)` (default top 10). Those get option ids `c1`, `c2`, …

### Why RRF

- Lucene and vector scores live on different scales; ranks are comparable.
- A document that is strong in **both** legs gets a higher fused score than one that is strong in only one.
- A document that appears in only one leg can still survive into the shortlist.

Example (same ranks on both legs):

| Situation | Fused contribution |
| --- | --- |
| Lucene #1 only | `1/(60+1) ≈ 0.0164` |
| Vector #1 only | `≈ 0.0164` |
| Both #1 | `≈ 0.0328` |
| Lucene #5 + Vector #2 | `1/65 + 1/62 ≈ 0.0315` |

### Spec-token annotation (materials only)

After fusion, for materials the pipeline extracts numeric/unit tokens from the **user** (e.g. `100mm`, `23`, `40/76`) via `spec_tokens`, and the same from each candidate’s label+detail text.

- `specTokens` — tokens found on the candidate
- `missingQuerySpecs` — query tokens not found on the candidate

These are **informational** for the UI and for the text sent to Jev. They do **not** currently change `fusedScore` or the sort order.

---

## 5. What the UI tabs show

| Tab | Source |
| --- | --- |
| Lucene | Fused rows that have a `lexicalRank`, sorted by that Lucene rank |
| Vector | Fused rows that have a `vectorRank`, sorted by that vector rank |
| Combined | Top `HYBRID_RESULT_LIMIT` by `fusedScore` |
| Final | Decision over the `sentToJev` shortlist (separate step) |

A row can appear in Lucene-only, vector-only, or both (`sources: ["lexical"]`, `["vector"]`, or both).

---

## 6. Hand-off to Jev

For each shortlisted candidate the pipeline builds `jevText`:

```text
<label> | <detail> | spec tokens: <up to 12 tokens>
```

(capped at 700 characters)

Jev then chooses among `c1…cN` plus `no_match`. That choice and its probabilities are independent of RRF; RRF only decides **who** is on the ballot.

---

## Code map

| Piece | File |
| --- | --- |
| Query cleanup | `normalize.py` |
| Fields / indexes per entity | `entities.py` |
| Lucene + vector pipelines, RRF, shortlist | `retrieve.py` |
| Orchestration + Jev call | `main.py` |
| Limits / index names | `.env` / `config.py` |
