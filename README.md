# SauMGM
## Sauen Management System - Small Business System

A small-business management system: contacts (clients, vendors, banks), a product/service catalog,
client subscriptions, invoicing, payments, bank deposits, expenses and sales tax. Everything specific
to one business is configuration, so it can be used by others.

Website: <https://www.saumgm.com/>. The design lives in [docs/design.md](docs/design.md).

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
.venv\Scripts\Activate.ps1    # Windows PowerShell (once per window)
# source .venv/Scripts/activate   # Windows Git Bash
# source .venv/bin/activate       # Linux / macOS
# PowerShell refuses to run the script? Once: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# Without activating, call the tools by path, e.g. .venv\Scripts\uvicorn ...
pip install -e ".[dev]"
cp .env.example .env          # then edit DATABASE_URL / TEST_DATABASE_URL

alembic upgrade head          # create/upgrade the database schema
uvicorn saumgm.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/api/docs - health check: http://127.0.0.1:8000/api/health

First login (after importing the Access data, or after `python -m saumgm create-organization
--name "My Company"` on a fresh install):

```sh
python -m saumgm create-user --email you@example.com --name "Your Name" --role owner
python -m saumgm set-password --email you@example.com      # later, to reset a password
```

Roles: **owner** (everything, including settings, users, audit log and unarchiving),
**bookkeeper** (day-to-day work: contacts, invoices, payments, expenses), **viewer** (read-only).

Files (business logo, issued invoice PDFs) go to `STORAGE_URL`, by default a git-ignored
`storage/` folder at the repository root; back it up together with the database.

The API uses a session cookie; requests that change data must also send the `X-CSRF-Token`
header with the value of the `saumgm_csrf` cookie (the frontend does this automatically).

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

End-to-end browser tests (Playwright) run against a separate API and database; see
[frontend/e2e/README.md](frontend/e2e/README.md).

## Production install (Ubuntu + Apache)

See [docs/deploy/ubuntu.md](docs/deploy/ubuntu.md): packages (with a check-and-install script,
`deploy/install-prereqs.sh`), database, systemd service, Apache vhost with HTTPS, backups, updates
and the switch-over from Access. The service, vhost, backup and update files are in [deploy/](deploy/).

Upgrading a server or the development PC to newer code, and the notes per version:
[docs/upgrading.md](docs/upgrading.md).

Several independent installations on one server (separate businesses, a demo, a test instance),
each in its own folder with its own database, port, web address and backups:
[docs/deploy/multiple-instances.md](docs/deploy/multiple-instances.md).

## Demo data

`python -m saumgm load-demo` fills an empty, migrated database with a made-up business: 10
clients, 5 vendors and about 15 months of invoices (including a credit note, a revision, a void
and a write-off), payments, deposits, expenses with receipts, subscriptions, sales tax with a
filing, a tax-exempt client and contact documents, dated relative to today. Sign in as
`owner@example.com`, `bookkeeper@example.com` or `viewer@example.com`, password `saumgm-demo`.

```sh
alembic upgrade head
python -m saumgm load-demo
```

It refuses to run on a database that already has a business. Use a separate database for it
(for development: a second database in `DATABASE_URL`; on a server: a demo instance).

## Importing the old MS Access database

A one-off importer moves the original Access application (`.mdb`) into SauMGM. It needs Windows
with the 64-bit Microsoft Access ODBC driver (installed with Office or the Access Database
Engine).

```sh
cd backend
pip install -e ".[dev,legacy]"
alembic upgrade head
cp saumgm/legacy_import/example_config.toml ../tmp/import_config.toml   # then fill it in
python -m saumgm.legacy_import --mdb ../tmp/sauen.com.mdb --config ../tmp/import_config.toml \
    --report ../tmp/import_report.md
```

What it does, in one transaction:

1. Copies every Access table verbatim into `legacy_*` tables (a read-only archive).
2. Creates the organization, maps contacts, catalog, invoices, payments, deposits and expenses
   into the new schema, keeping file and invoice numbers.
3. Reconciles counts and money totals per year against Access and writes a report listing
   every data issue. If anything does not match, the import is rolled back.

Add `--reset` to replace data from an earlier import. Keep the config and report out of git
(`tmp/` is ignored); they contain business data.

## Database changes

Change or add models in `backend/saumgm/models/`, then:

```sh
alembic revision --autogenerate -m "describe the change"
# review the generated file in backend/migrations/versions/, then
alembic upgrade head
```

A test fails if models and migrations are out of sync. Production runs MariaDB 10.11, and CI tests
against it, so don't use features from newer MariaDB versions.

## License

Copyright (C) 2026 J. Thomas Stokkeland - <https://www.saumgm.com/>

SauMGM is free software: you can redistribute it and/or modify it under the terms of the
[GNU General Public License](LICENSE) as published by the Free Software Foundation, either version
3 of the License, or (at your option) any later version. It is distributed in the hope that it
will be useful, but WITHOUT ANY WARRANTY; see the license for details.

The libraries it uses keep their own licenses, all compatible with the GPL; see
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). New source files start with the license header;
`python tools/license_headers.py` adds it, and CI checks it.
