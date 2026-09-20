# Deployment

This repo was originally built on the Emergent platform, which ran the frontend and
backend behind a single domain/proxy. Outside Emergent it's just two independent
services that talk to each other over HTTPS:

- **frontend/** — a Create React App (via craco) static site.
- **backend/** — a FastAPI + Motor (MongoDB) API server.

The frontend calls the backend at `${REACT_APP_BACKEND_URL}/api/...`, so the only
thing wiring the two together is that one environment variable.

## Backend (Render / Railway)

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
  (also provided as `backend/Procfile` for platforms that read one)
- Python version: 3.11 (see `backend/.python-version`)
- Database: a MongoDB Atlas cluster (or any MongoDB instance reachable from the
  backend host) — set `MONGO_URL` / `DB_NAME` accordingly.
- Configure the environment variables below.

## Frontend (Vercel)

- Root directory: `frontend`
- Framework preset: Create React App
- Build command: `yarn build` (or the platform default for CRA)
- `frontend/vercel.json` adds a catch-all rewrite to `index.html`, which is required
  because the app uses React Router's `BrowserRouter` — without it, deep links
  (e.g. refreshing on `/portal/dashboard`) 404 on Vercel's static hosting.
- Configure `REACT_APP_BACKEND_URL` to point at the deployed backend's public URL
  (no trailing slash).

## Environment variables

### Backend (`backend/.env`, see `backend/.env.example`)

| Variable | Required | Notes |
|---|---|---|
| `MONGO_URL` | yes | MongoDB connection string (e.g. MongoDB Atlas). |
| `DB_NAME` | yes | Database name. |
| `SANGLEY_TRUSTED_ORIGINS` | yes | Comma-separated list of allowed frontend origins, used for CORS. |
| `JWT_SECRET` | yes | Signs/verifies auth JWTs. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | yes | Bootstrap admin account credentials. |
| `PORTAL_DATA_KEY` | yes | Fernet key encrypting reseller-portal data at rest. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `FRONTEND_URL` | yes | Public URL of the deployed frontend, used to build referral links. |
| `STORAGE_APP_NAME` | yes | Namespace used when building storage object paths. |
| `INTEGRATION_PROXY_URL` | optional | Only needed to keep using Emergent's object-storage proxy for reseller-portal file uploads (`backend/portal/files.py`). Leave blank to disable that feature — uploads will 503 until you wire up your own storage backend. |
| `EMERGENT_LLM_KEY` | optional | Paired with `INTEGRATION_PROXY_URL` above. |

### Frontend (`frontend/.env`, see `frontend/.env.example`)

| Variable | Required | Notes |
|---|---|---|
| `REACT_APP_BACKEND_URL` | yes | Public URL of the deployed backend API (no trailing slash). |

## Known pre-existing behavior (not changed here)

`frontend/src/components/Elements.jsx` and `frontend/public/index.html` build
`og:image` and canonical URLs from `REACT_APP_BACKEND_URL`. This is a leftover from
Emergent's single-domain proxy setup, where that variable doubled as the site's
public URL. Once the frontend and backend are deployed on separate domains, those
specific SEO meta tags will point at the backend's domain instead of the frontend's.
This is flagged here as pre-existing behavior to be aware of, not something fixed in
this change, since the scope here is deployability only — not frontend/backend logic.
