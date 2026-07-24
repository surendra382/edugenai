# Feature: Core Infrastructure

**Phase:** 1 — Foundation
**ID:** phase1-f01
**Status:** Done
**Depends on:** —

---

## 1. Goal

Stand up the skeleton every later feature builds on: a runnable FastAPI app,
a runnable Streamlit app, a SQLite connection, and config loading — with
nothing business-specific in it yet. After this, F02/F03 only add
models/routes/pages, never touch project wiring.

## 2. Scope

### In Scope
- `requirements/base.txt` (+ `dev.txt` for pytest/httpx) with pinned versions
- App config loading from `.env` (DB path, API host/port) via `pydantic-settings`
- SQLAlchemy engine + session factory pointed at `data/app.db`
- FastAPI app (`backend/app/main.py`) that boots, creates tables on startup,
  exposes `GET /health`
- Streamlit entrypoint (`frontend/app.py`) that boots and can reach
  `GET /health` on the backend
- Base project package structure (`backend/app/{api,db,schemas}/__init__.py`)

### Out of Scope
- Any Subject/Chapter models or endpoints (F02/F03)
- Auth of any kind
- Docker/deployment

## 3. Data Model

None yet — just the engine/session plumbing and an empty `Base.metadata`
that later features register models against.

## 4. API Contract

| Method | Path | Response |
|--------|------|----------|
| GET | `/health` | `{"status": "ok"}` |

## 5. UI Behavior

Streamlit app loads, shows a title, and displays backend health
(green "Backend connected" / red "Backend unreachable") by calling
`/health`. No business UI yet.

## 6. Test Strategy

### Unit Tests
- Config loads expected values from a test `.env`

### Integration Tests
- `GET /health` returns 200 and `{"status": "ok"}` (via `httpx` + FastAPI
  `TestClient`)
- App startup creates `data/app.db` if it doesn't exist

### Manual Verification
- [ ] `uvicorn backend.app.main:app --reload` boots without error
- [ ] `streamlit run frontend/app.py` boots and shows "Backend connected"
- [ ] Stopping the backend flips the Streamlit indicator to "Backend unreachable"

## 7. Acceptance Criteria

- [ ] Both servers start cleanly from a fresh clone with only
      `pip install -r requirements/dev.txt`
- [ ] `pytest` passes with zero business logic tested (infra only)
- [ ] `.env.example` documents every required env var
