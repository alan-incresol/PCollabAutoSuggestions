# PCollab Search Suggestions

A vendor search application with autocomplete powered by MongoDB Atlas Search. The backend is a FastAPI service that runs aggregation queries against a MongoDB Atlas collection, and the frontend is a Next.js app that provides a real-time search UI.

## Prerequisites

- Python 3.10+
- Node.js 18+
- A MongoDB Atlas cluster with an Atlas Search index configured for autocomplete

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app (/health, /search)
│   ├── config.py            # Settings loaded from .env
│   ├── db.py                # MongoDB client setup
│   ├── requirements.txt     # Python dependencies
│   └── .env.example         # Environment variable template
└── frontend/
    ├── src/
    │   ├── app/page.tsx     # Search UI (client component)
    │   └── lib/api.ts       # API client
    ├── package.json
    └── .env.local.example   # Environment variable template
```

## Getting Started

### 1. Backend

```bash
cd backend
```

**Create a virtual environment and install dependencies:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Set up environment variables:**

```bash
cp .env.example .env
```

Edit `backend/.env` and fill in your values:

| Variable              | Required | Default                  | Description                            |
| --------------------- | -------- | ------------------------ | -------------------------------------- |
| `MONGODB_URI`         | Yes      | —                        | MongoDB Atlas connection string        |
| `MONGODB_DB`          | No       | `pcollab-quality`        | Database name                          |
| `COLLECTION_NAME`     | No       | `omOrgVendorDetails`     | Collection to search                   |
| `SEARCH_INDEX_NAME`   | No       | `vendorDetails-lucene`   | Atlas Search index name                |
| `CORS_ORIGINS`        | No       | `http://localhost:4000`  | Comma-separated allowed origins        |
| `SEARCH_RESULT_LIMIT` | No       | `50`                     | Max results returned per search        |

**Start the server:**

```bash
uvicorn main:app --reload --port 5000
```

The API will be available at `http://127.0.0.1:5000`. You can verify it's running by visiting `http://127.0.0.1:5000/health`.

### 2. Frontend

```bash
cd frontend
```

**Install dependencies:**

```bash
npm install
```

**Set up environment variables:**

```bash
cp .env.local.example .env.local
```

Edit `frontend/.env.local` if your backend is running on a different address (default is `http://127.0.0.1:5000`):

| Variable              | Default                  | Description      |
| --------------------- | ------------------------ | ---------------- |
| `NEXT_PUBLIC_API_URL`  | `http://127.0.0.1:5000` | Backend API URL  |

**Start the dev server:**

```bash
npm run dev -- -p 4000
```

Open `http://localhost:4000` in your browser.

## MongoDB Atlas Search Index

The backend expects an Atlas Search index (default name `vendorDetails-lucene`) on the target collection with **autocomplete** mappings on the fields used for search. Without this index, search queries will fail.

Refer to the [Atlas Search documentation](https://www.mongodb.com/docs/atlas/atlas-search/) for setup instructions.

## API Reference

### `GET /health`

Returns `{"status": "ok"}` when the server is running.

### `POST /search`

Search for vendors using autocomplete.

**Request body:**

```json
{
  "query": "acme",
  "fields": ["vendorName", "vendorCode"]
}
```

**Response:** An array of matching vendor documents (up to the configured limit).
