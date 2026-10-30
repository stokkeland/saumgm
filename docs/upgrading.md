# Upgrading SauMGM

How to move an installation (a server, or the development PC) to newer code, and what each
version needs beyond the usual steps. Read the section of the version you are moving to before
you start.

- [How versions are published](#how-versions-are-published)
- [Upgrading a server](#upgrading-a-server)
- [Upgrading the development PC](#upgrading-the-development-pc)
- [Checking the result](#checking-the-result)
- [Going back](#going-back)
- [Version notes](#version-notes): [2.1](#21-in-development), [2.0](#20), [1.0](#10)

New installations follow [deploy/ubuntu.md](deploy/ubuntu.md) and need none of this.

## How versions are published

| Where | What |
|---|---|
| `release/vX.Y` branches (`release/v1.0`, `release/v2.0`) | a released version and its fixes. Servers follow one of these. |
| tags `vX.Y.Z` (`v1.0.0`, `v2.0.0`, ...) | one exact version |
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

### From 1.0 to 2.0, step by step

Logged in as your admin account. **you** means without `sudo` when `/opt/saumgm` belongs to
you (`stat -c %U /opt/saumgm` prints your name); if it prints `root`, put `sudo` in front of
those lines too. **root** means with `sudo`. Never `sudo git` in a folder you own.

1. Read the [2.0 notes](#20) below: what changes, what the upgrade deletes (the `legacy_*`
   tables) and what to check afterwards.
2. **root**: add the new settings to `.env` (it belongs to root):
   ```sh
   sudo nano /opt/saumgm/backend/.env
   ```
   ```ini
   EMAIL_URL=resend://
   RESEND_API_KEY=re_...                # Resend → API Keys, "Sending access"
   APP_URL=https://saumgm.example.com   # the address you open the app at
   ```
   Without them 2.0 runs as well; it just sends no email (messages go to the log). Resend needs
   your domain verified first ([deploy/ubuntu.md, section 4](deploy/ubuntu.md#4-configuration)).
3. **you**: switch the checkout to 2.0:
   ```sh
   cd /opt/saumgm
   git status                     # must say "nothing to commit"; undo hand edits first
   git fetch origin
   git switch release/v2.0
   git log -1 --oneline           # the 2.0 code is now in place
   ```
4. **root**: run the 2.0 update script on the code now there. It backs up the database and
   files first, then installs the Python packages, runs the migrations, builds the frontend,
   restarts the API and checks the health:
   ```sh
   sudo /opt/saumgm/deploy/update.sh --no-pull
   ```
   (Steps 3 and 4 in one: `sudo /opt/saumgm/deploy/update.sh --branch release/v2.0` works
   when the server has the latest `release/v1.0`, whose script knows `--branch`; the script of
   the `v1.0.0` tag itself does not.)
5. **root**: install the timer for the daily reminders digest (new in 2.0; `update.sh` does
   not install units):
   ```sh
   sudo cp /opt/saumgm/deploy/systemd/saumgm-notify.service /opt/saumgm/deploy/systemd/saumgm-notify.timer /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now saumgm-notify.timer
   ```
6. **In the app** (as an owner): Admin → Email: set the sender and press "Send test"; Admin →
   Reminders: who gets the digest.
7. [Check the result](#checking-the-result) and the "After upgrading, check" list in the
   [2.0 notes](#20).

If anything goes wrong, [go back](#going-back) with the backup from step 4.

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
3. `cd /opt/saumgm && git switch release/v1.0` (the version you came from), as the folder's
   owner: without `sudo` if it is yours.
4. `sudo deploy/update.sh --no-pull`

Anything entered after the upgrade is lost, so decide quickly, and keep the backup until the new
version has run for a few days.

## Version notes

### 2.1 (in development)

Being built on `main` (version `2.1.0.dev0`). Nothing beyond the usual update steps yet; this
list grows with every merged pull request.

### 2.0

Released as `release/v2.0`, tag `v2.0.0`; built as described in [plan-v2.md](plan-v2.md). From
1.0, follow [the steps above](#from-10-to-20-step-by-step).

**New settings (`.env`)**, all optional (without them nothing is sent; messages only go to
the log). See [deploy/ubuntu.md, section 4](deploy/ubuntu.md#4-configuration):

| Setting | Server | Development PC |
|---|---|---|
| `EMAIL_URL` | `resend://` | leave out (`console://`), or `resend://` to try real sending |
| `RESEND_API_KEY` | your Resend API key | only with `resend://` |
| `EMAIL_FROM` | optional; the sender is set in Admin → Email | optional |
| `EMAIL_REDIRECT_TO` | leave out | **your own address**: the development database holds real client addresses |
| `APP_URL` | the address you open the app at, `https://...` (links in the reminders digest) | `http://localhost:5173` |

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
- Email (Resend): invoices, credit notes and payment receipts can be sent by email with their
  PDF, from the invoice or payment page. Admin → Email holds the sender, the message templates
  and a log of every message sent; each sent email also shows in the record's History. After
  upgrading, set the sender in Admin → Email and press "Send test".
- The History tab shows the values of events such as "issue" and "revise" correctly (1.0
  showed only one character of them, and could fail on a revised invoice).
- Invoice lines have a SKU, copied from the catalog item when the line is saved (existing lines
  are filled from their item). It shows on the invoice screen, in the editor and on the PDF
  when a line has one. PDFs of invoices issued before the upgrade stay as they were.
- Reports: the sales report and the profit & loss can count income **by invoice date** (as in
  1.0) or **by payment date**. The default is a new business setting, "Report income by" (Admin
  → Settings → Business), which the upgrade sets to the same choice as "Report tax by"; each
  report screen can switch it.
- Every report has **PDF** (opens in the browser, to save or print), **CSV** and **Email**
  buttons. Emailed reports go to yourself unless you change the recipient; their message has a
  template in Admin → Email. Report CSVs now have the column headings shown on the screen,
  include the total row, and their file names say the basis
  (`sales-by-month-accrual-2026-01-01-2026-12-31.csv`).
- Subscriptions: a client subscription has **lines** (hosting and a domain on one subscription
  and one invoice). The upgrade turns each subscription into one with a single line. Where a 1.0
  subscription had vendor details (vendor, vendor renewal date, our cost), a **vendor
  subscription** is made from them and linked; a cost without a vendor is kept in the
  subscription's notes. Invoices already billed keep their link to the subscription.
- The billing run makes **one draft invoice per subscription** (1.0 made one per client); tick
  "One invoice per client for subscriptions due on the same day" for the old behaviour.
- New: **Money → Vendor subscriptions**, what you pay for regularly, with "Record payment" (makes
  the expense and moves the next due date on), and **Catalog → Packages** to fill a new
  subscription's lines.
- `/api/subscriptions` takes and returns `lines`; `vendor_party_id`, `vendor_renewal_date` and
  `unit_cost` are gone from it (see `/api/vendor-subscriptions`), as is the
  `vendor_renewal_through` filter. The dashboard's renewals have `summary` instead of
  `item_name`.
- New: **To do** (`/todo`, and a To do card on the dashboard instead of the expiring-documents
  card): clients to bill, vendors to pay, overdue invoices, expiring documents. **Admin →
  Reminders** sets how many days ahead (14 for billing, 10 for vendor payments, the new
  `organization.remind_*` columns) and who gets the digest (empty: the owners).
- New: the **reminders digest** email and `python -m saumgm notify`, run daily by a new timer.
  The timer is not installed by `update.sh`; install it once:
  ```sh
  sudo cp /opt/saumgm/deploy/systemd/saumgm-notify.service /opt/saumgm/deploy/systemd/saumgm-notify.timer /etc/systemd/system/
  sudo systemctl daemon-reload && sudo systemctl enable --now saumgm-notify.timer
  ```
  (instances: `saumgm-notify@.service` and `saumgm-notify@NAME.timer`, see
  [deploy/multiple-instances.md](deploy/multiple-instances.md#9-backups)).
- New: **Money → Bank accounts**: checking, savings and card accounts, each with a register
  that starts at an opening balance on a day you choose, transfers (paying the card) and
  reconciling with statements. Nothing is filled in by the upgrade: add your accounts, then
  choose "Deposit to" on new deposits and "Paid from" on expenses and vendor subscriptions.
  Older deposits can be given an account on their page (if dated after the register starts).
- The to-do list has a **Banking** section (accounts not reconciled for 35 days; Admin →
  Reminders changes it).
- New: **Operations → Assets** (equipment and licenses, your own and clients'; a contact's
  page has an Assets tab) and **Admin → Asset categories**. The upgrade gives every business the
  default categories (Laptop, Server, Network, Software license...). The to-do list has an
  **Assets** section for warranties and support contracts ending (30 days; Admin → Reminders).
- New: **Operations → Knowledge base**: articles in Markdown with a live preview, a
  category tree, search, every saved version, images and files, PDF, and "Email to…" for
  published, shareable articles (a contact's page has an Articles tab). Starts empty. The email
  text can be changed in Admin → Email (the new "Knowledge base article" template).
- Version `2.0.0` (Admin → About and `/api/health`).

**After upgrading, check:** `/api/health` shows `"schema_current":true`; Admin → Email →
"Send test" arrives (servers with `resend://`); Sales → Subscriptions and Money → Vendor
subscriptions show what you had (a vendor subscription made by the upgrade says so in its notes;
give it an expense account before recording a payment if its item had no cost account);
`sudo -u saumgm .venv/bin/python -m saumgm notify --dry-run` (from `/opt/saumgm/backend`)
prints the digest, and Admin → Reminders → "Send now" delivers one.

### 1.0

The first release (`release/v1.0`, tag `v1.0.0`): everything in
[design.md](design.md#7-phases) phases 1 to 6, contact documents, demo data, several instances.
Installed fresh with the `docs/deploy/ubuntu.md` of a `release/v1.0` checkout; no upgrade
steps.
