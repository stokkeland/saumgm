# SauMGM
## Sauen Management System - Small Business System

A small-business management system: contacts (clients, vendors, banks), a product/service catalog,
client subscriptions, invoicing, payments, bank deposits, expenses and sales tax. Everything specific
to one business is configuration, so it can be used by others.

Status: early development. The design lives in [docs/design.md](docs/design.md).

| Part | Stack |
|---|---|
| [backend/](backend/) | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, MariaDB 10.11+ |
| [frontend/](frontend/) | React, TypeScript, Vite, Mantine, TanStack Query |

## Development setup

Prerequisites: Python 3.12+, Node.js 24, a MariaDB 10.11+ server with an empty database and a user
that owns it (and may create a `test_*` database for the test suite).

### Backend

```sh
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows (Git Bash: source .venv/Scripts/activate)
# source .venv/bin/activate   # Linux / macOS
pip install -e ".[dev]"
cp .env.example .env          # then edit DATABASE_URL / TEST_DATABASE_URL

alembic upgrade head          # create/upgrade the database schema
uvicorn saumgm.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/api/docs - health check: http://127.0.0.1:8000/api/health

Checks (the same ones CI runs):

```sh
ruff check . && ruff format --check . && mypy saumgm tests && pytest
```

The test suite drops and recreates the database named in `TEST_DATABASE_URL` (it must start with
`test_`).

### Frontend

```sh
cd frontend
npm install
npm run dev                   # http://localhost:5173, proxies /api to the backend on :8000
```

After changing the API, regenerate the TypeScript types (backend must be running):

```sh
npm run gen:api
```

Other scripts: `npm run lint`, `npm run typecheck`, `npm run build`.

## Database changes

Change or add models in `backend/saumgm/models/`, then:

```sh
alembic revision --autogenerate -m "describe the change"
# review the generated file in backend/migrations/versions/, then
alembic upgrade head
```

A test fails if models and migrations are out of sync. Production runs MariaDB 10.11, and CI tests
against it, so don't use features from newer MariaDB versions.
