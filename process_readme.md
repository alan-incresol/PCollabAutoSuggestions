# How This App Works (Process Guide)

This file explains, in plain language, what happens from the moment you start the app
to the moment you see search results on screen.

---

## 1. The Big Picture

The app has **three parts** that talk to each other:

```
 ┌──────────────┐      ┌──────────────────┐      ┌───────────────────────┐
 │   Browser    │ ───► │  Frontend         │ ───► │  Backend              │ ───► MongoDB Atlas
 │  (you type)  │ ◄─── │  Next.js :4000    │ ◄─── │  FastAPI :5000        │ ◄─── (Atlas Search)
 └──────────────┘      └──────────────────┘      └───────────────────────┘
```

| Part | What it is | What it does |
|------|-----------|--------------|
| **Frontend** | Next.js + React + Tailwind (folder `frontend/`) | Shows the search page and sends your typing to the backend |
| **Backend** | Python FastAPI (folder `backend/`) | Builds the search query and asks MongoDB for matches |
| **Database** | MongoDB Atlas with **Atlas Search** indexes | Stores the data (PRs, POs, RFQs, vendors, ...) and does the fast "autocomplete" matching |

In one sentence: **you type → the backend asks Atlas Search "what starts like this?" → you get a
dropdown of suggestions → you click one → you get the full matching documents.**

---

## 2. What Each File Does

### Backend (`backend/`)

| File | Job in simple words |
|------|---------------------|
| `main.py` | The "front desk". Starts the API and defines the endpoints: `/health`, `/config`, `/suggest`, `/search`. |
| `config.py` | Reads settings from `backend/.env` (database link, which collection to use, etc.). It re-reads the file whenever it changes, so you don't need to restart. |
| `db.py` | Opens (and reuses) the connection to MongoDB. |
| `search_registry.py` | A "phone book". For each collection it lists the Atlas index name and which fields can be searched, plus where those fields live inside the document. |
| `requirements.txt` | Python libraries needed: `fastapi`, `uvicorn`, `pymongo`, `pydantic-settings`, `python-dotenv`. |
| `.env.example` | Template for your `.env` settings file. |

### Frontend (`frontend/`)

| File | Job in simple words |
|------|---------------------|
| `src/app/page.tsx` | The whole search screen: inputs, field buttons, dropdown, results. |
| `src/lib/api.ts` | Small helper functions that call the backend (`fetchAppConfig`, `suggestPR`, `searchPR`). |
| `src/app/layout.tsx` | Page wrapper (title, global CSS). |
| `next.config.ts` | Forwards (proxies) `/config`, `/suggest`, `/search`, `/health` from port 4000 to the backend on port 5000. |
| `.env.local.example` | Template: `API_PROXY_TARGET` (where the backend is). |

---

## 3. Step by Step: Starting Up

### Step A — Backend starts

You run `python main.py` (or `uvicorn main:app --port 5000`) inside `backend/`.

1. `config.py` loads `backend/.env`. Settings it looks for:
   - `MONGODB_URI` — the database connection string (**required**)
   - `MONGODB_DB` — database name (default `vendor_portal_qas`)
   - `COLLECTION_NAME` — which collection to search (default `PurRequisitions`)
   - `SEARCH_INDEX_NAME` — default `pr`
   - `CORS_ORIGINS` — which websites may call the API (default `http://localhost:4000`)
   - `SEARCH_RESULT_LIMIT` — max documents per search (default `50`)

   Values in `backend/.env` win over system environment variables.
2. `main.py` prints which settings file it loaded and which DB / collection / index it will use.
3. It turns on **CORS** so the browser is allowed to talk to it.
4. The server now listens on **port 5000**.

> The MongoDB connection is not opened yet — `db.py` opens it the first time a search happens,
> then keeps reusing it. If `MONGODB_URI` changes in `.env`, it closes the old one and opens a new one.

### Step B — Frontend starts

You run `npm run dev` inside `frontend/`. Next.js starts on **port 4000**.
Any browser call to `/config`, `/suggest`, `/search` or `/health` on port 4000 is quietly
forwarded to the backend on port 5000 (see `next.config.ts`). This means the browser only ever
talks to one address.

---

## 4. Step by Step: Using the Page

### Step 1 — Page loads and asks "what am I searching?"

When you open `http://localhost:4000`:

1. The page calls **`GET /config`**.
2. The backend reads `COLLECTION_NAME` from `.env` and looks it up in `search_registry.py`.
3. It replies with:
   - the collection name (e.g. `PurRequisitions`)
   - the Atlas index name (e.g. `pr`)
   - whether **Org OPU ID** is needed (`requiresOrgOpuId`)
   - the list of searchable fields, each with a friendly label
     (e.g. `prNum` → "PR Num", `matrNo` → "Material Number")
4. The page draws the field buttons from that list.

The page also re-asks for `/config` whenever you come back to the browser tab. So if you change
`COLLECTION_NAME` in `.env`, just switch back to the tab — the page updates itself and clears the
old inputs.

### Step 2 — You fill in the organisation filters

- **Org ID** — always required.
- **Org OPU ID** — required for most collections. Not shown for vendor master
  (`OmOrgVendorDetails`), because that one doesn't need it.

The search box stays **disabled** until these are filled in. This makes sure people only see
their own organisation's data.

### Step 3 — You (optionally) pick fields

Click field buttons such as "PR Num" or "Material Desc" to search only in those fields.
If you pick **none**, it searches **all** fields for that collection.

### Step 4 — You type → suggestions appear (`POST /suggest`)

1. The page waits **280 ms** after you stop typing (so it doesn't call the server on every key).
   If you keep typing, the old request is cancelled.
2. It sends `POST /suggest` with: your text, chosen fields, Org ID, Org OPU ID.
3. The backend:
   1. Checks the collection name is known (else error 400).
   2. Checks Org OPU ID is present if needed (else error 400).
   3. Checks the chosen fields are allowed for this collection (else error 400).
   4. Builds an Atlas Search query (see section 5).
   5. Runs it on MongoDB and gets up to 50 matching documents.
   6. From each document it pulls out the values of the chosen fields
      (it can dig through nested objects and lists), keeps only values that contain your text,
      removes duplicates (ignoring upper/lower case), and sorts them A→Z.
4. The backend returns a simple list of strings, e.g. `["PR-1001", "PR-1002"]`.
5. The page shows them in a dropdown.

### Step 5 — You click a suggestion → full results (`POST /search`)

1. The chosen text goes into the box and the dropdown closes.
2. The page sends `POST /search` with the same details.
3. The backend runs the **same** Atlas Search query, but this time returns the **whole documents**
   (it converts MongoDB IDs into normal text so they can be sent as JSON).
4. The page shows "N results for ..." and a card for each document: a short summary line
   (from the first 3 fields) and the full JSON below it.

Typing again, changing fields, or changing Org IDs clears the old results. The **✕** button
clears everything.

---

## 5. What the Search Query Looks Like

For every suggest/search, the backend builds one MongoDB `$search` step like this:

```
$search on index "<index name>":
   MUST match (filters):
      - markAsDelete = false          (hide deleted records)
      - orgId = <your Org ID>
      - orgOpuId = <your Org OPU ID>  (only if the collection needs it)
   SHOULD match (at least 1):
      - autocomplete "<your text>" on field 1
      - autocomplete "<your text>" on field 2
      - ...
then $limit 50
```

"Autocomplete" means Atlas matches words that **start with** what you typed, so typing `PR-10`
finds `PR-1001`. This only works if the Atlas Search index has autocomplete set up on those fields.

---

## 5b. Vendor Name Spelling Correction (Jev)

For the vendor collection (`OmOrgVendorDetails`), when the search includes **Company Name**
(or all fields), the backend tries to fix spelling mistakes before searching:

1. **Find nearby names** — a *fuzzy* Atlas Search (up to 2 typos allowed) on the same
   `vendor-master` index, with the same Org ID filters, collects real company names close to what
   was typed. Nothing in the index is changed; fuzzy is just a query option.
2. **Skip if not needed** — if the text is shorter than 3 characters, or already appears in a real
   name (e.g. a correct prefix like "Acme Ind"), it is searched as typed and Jev is not called.
3. **Ask Jev** — the typed text and the nearby names go to Jev (TypeSafe AI, `typesafe-sdk`) as a
   *Choice* question: "which of these did the user mean?", with an extra option "none of them".
   Jev only *picks* from real names; it never makes one up.
4. **Search with the pick** — if Jev is confident (≥ 0.6 by default), the normal search runs with
   the corrected name.
5. **Fallback** — if Jev fails, times out, is not configured, says "none", is unsure, or the
   corrected name finds nothing, the search runs with the original text exactly as before.

Settings in `backend/.env`: `TYPESAFE_API_KEY` (empty = correction off), and optionally
`TYPESAFE_MODEL`, `CORRECTION_TIMEOUT_SECONDS`, `CORRECTION_MIN_CONFIDENCE`.
To correct another field later (e.g. material descriptions), add it to `correctable_fields` for that
collection in `search_registry.py`. Code lives in `backend/correction.py`; tests in
`backend/tests/test_correction.py`.

---

## 6. Collections the App Knows About

Defined in `backend/search_registry.py`:

| Collection | Atlas index | Needs Org OPU ID? |
|-----------|-------------|-------------------|
| `PurRequisitions` | `pr` | Yes |
| `OmOrgPurOrders`, `PurchaseOrders` | `po` | Yes |
| `RfqData` | `rfq_data` | Yes |
| `MaterialMaster` | `material-master` | Yes |
| `OmOrgVendorDetails` | `vendor-master` | **No** |
| `OmOrgPurInvoices`, `Invoices` | `invoices` | Yes |

Collection names are matched without caring about upper/lower case. To switch collections,
change `COLLECTION_NAME` in `backend/.env` (no restart needed). To add a new collection, add a
field map and an entry in `COLLECTION_REGISTRY`.

---

## 7. Full Flow in One Picture

```
Start backend (port 5000) ── loads backend/.env
Start frontend (port 4000) ── proxies API calls to 5000
        │
        ▼
Open page ──► GET /config ──► registry lookup ──► field buttons drawn
        │
        ▼
Enter Org ID (+ Org OPU ID) ──► search box unlocked
        │
        ▼
Pick fields (optional)
        │
        ▼
Type text ──(wait 280ms)──► POST /suggest
        │                      └─► validate ─► $search on Atlas ─► pull matching values
        │                          ─► dedupe + sort ─► list of strings
        ▼
Dropdown of suggestions
        │
        ▼
Click one ──► POST /search ──► same $search ─► full documents
        │
        ▼
Results shown as cards
```

---

## 8. When Things Go Wrong

| What you see | Likely cause |
|--------------|-------------|
| "Fix backend config to search" / config error | Backend is not running, or `COLLECTION_NAME` is not in the registry |
| `400 orgOpuId is required` | Org OPU ID left empty for a collection that needs it |
| `400 Unknown fields` | A field was sent that this collection doesn't have |
| `502 Suggest failed` / `Search failed` | MongoDB problem: wrong `MONGODB_URI`, missing Atlas Search index, or index name mismatch |
| No suggestions at all | Atlas index has no autocomplete mapping on those fields, or Org IDs don't match any data |

Quick check: open `http://localhost:5000/health` — it should say `{"status": "ok"}`.
