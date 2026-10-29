# Upgrading SauMGM

How to move an installation (a server, or the development PC) to newer code, and what each
version needs beyond the usual steps. Read the section of the version you are moving to before
you start.

- [How versions are published](#how-versions-are-published)
- [Upgrading a server](#upgrading-a-server)
- [Upgrading the development PC](#upgrading-the-development-pc)
- [Checking the result](#checking-the-result)
- [Going back](#going-back)
- [Version notes](#version-notes): [2.0](#20-in-development), [1.0](#10)

## How versions are published

| Where | What |
|---|---|
| `release/vX.Y` branches (`release/v1.0`, later `release/v2.0`) | a released version and its fixes. Servers follow one of these. |
| tags `vX.Y.Z` (`v1.0.0`, ...) | one exact version |
| `main` | the next version while it is being built; changes arrive through pull requests |

The running version is in `/api/health` (`"version"`), see [Checking the result](#checking-the-result).

Database changes are Alembic migrations. They run automatically during an update, only ever move
forward, and are listed per version below, with a warning when one deletes data.

## Upgrading a server

**Fixes within the same version** (for example the latest `release/v1.0`):

```sh
sudo /opt/saumgm/deploy/update.sh
```

The script backs up the database and files, pulls the branch that is checked out, installs the
Python packages, runs the migrations, builds the frontend (if Node.js is installed), restarts
the API and waits for the health check. It stops if files in `/opt/saumgm` were edited by hand,
and it fails if the database schema is not the newest one afterwards.

**Moving to a new version** (for example from 2.0 to 2.1):

1. Read the version notes below, for every version you skip as well.
2. Add any new settings to `/opt/saumgm/backend/.env`.
3. Switch and update in one go:
   ```sh
   sudo /opt/saumgm/deploy/update.sh --branch release/v2.1
   ```
4. [Check the result](#checking-the-result).

**From 1.0 to 2.0**, once `release/v2.0` exists: the update script that came with 1.0 does not
know `--branch` yet, so the switch is done by hand the first time:

```sh
cd /opt/saumgm
git fetch origin                         # with sudo only if root owns /opt/saumgm
git switch release/v2.0
sudo deploy/update.sh --no-pull          # backup, packages, migrations, frontend, restart
```

**Several instances:** add `--instance NAME` to every `update.sh` call, and use the instance's
folder (`/opt/saumgm-NAME`). Update the test instance first; see
[deploy/multiple-instances.md](deploy/multiple-instances.md#updating).

## Upgrading the development PC

In Git Bash, from the repository folder. After a pull request has been merged into `main`:

```sh
git switch main
git pull
cd backend
.venv/Scripts/pip install -e ".[dev,legacy]"     # new or changed Python packages
.venv/Scripts/alembic upgrade head               # new tables and columns
cd ../frontend
npm ci                                           # new or changed frontend packages
```

Then restart the API (`uvicorn ...`) and the frontend (`npm run dev`) if they are running.

Every pull request lists in its description what it needs from these steps (most need only the
pull and `alembic upgrade head`), plus any new `.env` settings.

**Trying a pull request before it is merged:** the same steps with `git switch feature/<topic>`
instead of `main`. Its migrations then change the development database, and switching back to
`main` does not undo them. Either:

- try branches on a copy of the database (see the E2E setup in
  [frontend/e2e/README.md](../frontend/e2e/README.md) for how to make one), or
- note `alembic current` before switching to the branch, and undo the branch's migrations
  **before** switching away, while its migration files are still there:
  `alembic downgrade <the revision you noted>`.

**Following a released version** instead of `main` (to reproduce what a server runs):
`git switch release/v1.0 && git pull`, and the same backend and frontend steps. A database
that has already been migrated by newer code cannot go back this way; use a copy.

## Checking the result

```sh
curl -s http://127.0.0.1:8000/api/health          # on the server (instances: their port)
curl -s http://localhost:8000/api/health          # on the development PC
```

```json
{"status":"ok","version":"2.0.0","database":"ok","database_version":"10.11.13-MariaDB...",
 "schema_revision":"48d37bf42439","schema_current":true}
```

- `version`: the code that is running.
- `schema_current: true`: the database has every migration of that code. `false` means
  `alembic upgrade head` has not run (or failed); `update.sh` reports this as an error.
  (`schema_revision` and `schema_current` are new in 2.0.)

Then sign in and open a few pages, as listed in the version notes.

## Going back

Migrations only move forward, so going back to an older version means restoring the backup that
`update.sh` made before the upgrade:

1. `sudo systemctl stop saumgm`
2. Restore the database and files from `/var/backups/saumgm` (the newest `saumgm-db-...` and
   `saumgm-files-...` from before the upgrade), as in
   [deploy/ubuntu.md, section 9](deploy/ubuntu.md#9-backups).
3. `cd /opt/saumgm && git switch release/v1.0` (the version you came from; `sudo git` if root
   owns the folder).
4. `sudo deploy/update.sh --no-pull`

Anything entered after the upgrade is lost, so decide quickly, and keep the backup until the new
version has run for a few days.

## Version notes

### 2.0 (in development)

Being built on `main`; see [plan-v2.md](plan-v2.md). This list grows with every merged pull
request.

**New settings (`.env`):** none yet.

**Data removed by migrations:**

- The `legacy_*` tables (20 in the first installation): the verbatim copies of the MS Access
  tables that the importer made. The application never read them. Everything imported from
  them stays, including each record's "Old system" tab (`legacy_data`) and the old tax amounts
  the reports use. To keep a copy, the backup `update.sh` makes before migrating has them, as
  do the 1.0 SQL export and the original `.mdb`.

**Changes:**

- `/api/health` also reports `schema_revision` and `schema_current`; `update.sh` fails when the
  schema is not current after an update.
- `update.sh --branch NAME` switches to another branch before pulling, and continues with the
  newly pulled copy of itself, so each version's own update steps are used.
- `update.sh` refuses to pull over files edited by hand in the installation folder.
- `update.sh` runs git, pip and npm as the owner of the installation folder, which can be your
  admin account instead of root ([deploy/ubuntu.md, section 3](deploy/ubuntu.md#3-code-and-python-environment)).
- The menu is grouped (Sales, Money, Reports, Admin) and the groups fold. Settings, Users
  (formerly a Settings tab), the audit log and a new About page (versions) are under Admin, at
  `/admin/...`; the old `/settings` and `/audit` addresses redirect there.
- Invoice lines have a SKU, copied from the catalog item when the line is saved (existing lines
  are filled from their item). It shows on the invoice screen, in the editor and on the PDF
  when a line has one. PDFs of invoices issued before the upgrade stay as they were.
- Version numbers: `2.0.0.dev0` (backend) and `2.0.0-dev.0` (frontend) during development.

**After upgrading, check:** `/api/health` shows `"schema_current":true`.

### 1.0

The first release (`release/v1.0`, tag `v1.0.0`): everything in
[design.md](design.md#7-phases) phases 1 to 6, contact documents, demo data, several instances.
Installed fresh with [deploy/ubuntu.md](deploy/ubuntu.md); no upgrade steps.
