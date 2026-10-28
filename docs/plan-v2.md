# SauMGM 2.0 plan

Status: **draft for review**. Nothing here is built yet. Decisions marked **(decide)** need an
answer before that part starts; each has a recommendation.

Version 1.0 is on the branch `release/v1.0`. 2.0 is developed on `main`, one feature branch and
pull request per part below, so it can be built, reviewed and merged a piece at a time.

Contents:

1. [Branches, versions and upgrading](#1-branches-versions-and-upgrading)
2. [Order of work](#2-order-of-work)
3. [The parts](#3-the-parts)
   - [A. Clean-up: legacy tables, SKU on invoices](#a-clean-up-legacy-tables-sku-on-invoices)
   - [B. Layout: modules and an Admin section](#b-layout-modules-and-an-admin-section)
   - [C. Email (Resend)](#c-email-resend)
   - [D. Reports: income by payment date, PDF/print, email](#d-reports-income-by-payment-date-pdfprint-email)
   - [E. Subscription packages](#e-subscription-packages)
   - [F. Banking: accounts and registers](#f-banking-accounts-and-registers)
   - [G. Assets (CMDB, first step)](#g-assets-cmdb-first-step)
   - [H. Knowledge base](#h-knowledge-base)
4. [Decisions needed](#4-decisions-needed)

---

## 1. Branches, versions and upgrading

### Branches

| Branch | Purpose |
|---|---|
| `main` | development of the next version (2.0). Always passes CI. |
| `feature/<topic>` | one part of the plan; Claude creates it from `main`, opens a pull request, the owner reviews and merges |
| `release/v1.0` | the deployed 1.0. Only fixes go here (a fix branch from `release/v1.0`, PR into it, then the same fix onto `main`) |
| `release/v2.0` | created from `main` when 2.0 is finished; servers move to it |

Tags mark exact versions: `v1.0.0` on the current tip of `release/v1.0` (to be added), `v2.0.0`
when 2.0 is released, `v2.0.1` for a fix after that.

### Version numbers

Both `backend/pyproject.toml` and `frontend/package.json` still say `0.1.0`. Set them to
`2.0.0.dev0` on `main` now and `2.0.0` at release, and show the version in the app (Admin →
About, and in `/api/health`), so it is always clear which version a server runs.

### Upgrading

Schema changes are Alembic migrations, as in 1.0: `alembic upgrade head` applies whatever is
new, and `deploy/update.sh` already runs it after a backup. Two additions:

- **`update.sh --branch release/v2.0`** switches the checkout to another branch before pulling.
  Without `--branch` it pulls the branch already checked out, as now.
- **`docs/upgrading.md`**: one section per version with anything beyond running the script: new
  `.env` settings (email in 2.0), data the upgrade removes (legacy tables, see A), and anything
  to check afterwards. Every migration that deletes data says so in that file.

Upgrading a **server** from 1.0 to 2.0 then becomes:

```sh
sudo /opt/saumgm/deploy/backup.sh                         # update.sh also does this
sudo nano /opt/saumgm/backend/.env                        # add the new settings (docs/upgrading.md)
sudo /opt/saumgm/deploy/update.sh --branch release/v2.0
```

Upgrading the **development PC** (Git Bash, from the repository folder) after a pull request is
merged:

```sh
git switch main && git pull
cd backend
.venv/Scripts/pip install -e ".[dev,legacy]"              # new or changed dependencies
.venv/Scripts/alembic upgrade head                        # new tables and columns
cd ../frontend && npm ci                                  # new frontend dependencies
```

To try a feature branch before it is merged, the same steps with `git switch feature/<topic>`.
A branch whose migration has run cannot simply be switched away from: run
`alembic downgrade -1` first, or (simpler) try branches on a copy of the database. Every pull
request lists the steps it needs in its description.

## 2. Order of work

Each step is one pull request into `main`. The order puts shared foundations first (layout,
email) and keeps each step reviewable.

| # | Part | Why here | Size |
|---|---|---|---|
| 0 | This plan, `docs/upgrading.md`, `update.sh --branch`, versions, tag `v1.0.0` | sets up everything after it | S |
| 1 | A. Clean-up: drop legacy tables, SKU on invoices | small, independent | S |
| 2 | B. Layout: modules, grouped navigation, Admin section | every new module plugs into it | M |
| 3 | C. Email (Resend), first use: email an invoice or receipt | reports and the knowledge base reuse it | M |
| 4 | D. Reports: income by payment date, PDF/print, email a report | uses C | M |
| 5 | E. Subscription packages | flushes or converts subscription data | M |
| 6 | F. Banking | the biggest new area | L |
| 7 | G. Assets | new module | M |
| 8 | H. Knowledge base | new module, uses C | M |
| 9 | Release 2.0: `release/v2.0`, tag `v2.0.0`, upgrade the server | | S |

The order of 5–8 can change freely; they do not depend on each other.

## 3. The parts

### A. Clean-up: legacy tables, SKU on invoices

**Legacy tables.** The database has 21 `legacy_*` tables (`legacy_tblinvoicehdr`, ...). They
are verbatim copies of the Access tables, written once by the importer; the application never
reads them. A migration drops them. Before it runs, `update.sh` makes a backup, and the original
`.mdb` and the 1.0 SQL export remain the reference.

What stays, because 1.0 data depends on it:

| Kept | Used for |
|---|---|
| `payment_allocation.legacy_sales_tax`, `legacy_taxable_amount` | cash-basis sales-tax report for old payments (Access stored tax per payment) |
| `invoice_line.legacy_unit_tax` | the tax column on old invoices |
| `legacy_id` columns | links back to the Access record numbers; harmless |
| `legacy_data` (JSON per contact, invoice, expense, ...) | the "Old system" tab; small. **(decide)** keep, or drop with the tables |

The importer keeps working (it recreates the copies only when it is run on a new database).

**SKU on invoices.** Invoice lines get their own `sku` column, copied from the catalog item when
the line is saved, the same way the description is copied: changing a catalog SKU later must
not change an issued invoice. Existing lines are filled from their catalog item. The SKU shows
as a column (or before the description) on the invoice screen, the editor and the PDF, only
when at least one line has one. PDFs of already-issued invoices are stored as issued and do not
change; a revision or a new invoice shows the SKU.

### B. Layout: modules and an Admin section

**Navigation in groups** instead of one long list, so new modules have an obvious place:

```
Dashboard
Sales          Contacts · Invoices · Payments · Subscriptions · Catalog
Money          Banking · Deposits · Expenses
Operations     Assets · Knowledge base
Reports
Admin          Settings · Users · Email · Audit log · About      (owner)
```

Groups fold open and closed; on a phone the same menu is in the drawer.

**Modules in the code.** Each area becomes a folder that declares its own routes and menu entries:
`frontend/src/modules/<name>/` (pages, components, `module.ts` with routes and nav items), and
the shell builds routes and navigation from the list of modules. On the backend each module
already has its own router, models, schemas and service; that stays, with one registry for
routers. Adding a module then means adding a folder and one line, without touching the shell.

**Admin section.** Settings, Users (moved out of Settings), Email settings, Audit log and About
(version, database version) move under `/admin`. Only owners see it, as with the audit log now;
bookkeepers keep read access where they have it today.

**Turning modules off.** Admin → Modules can hide Banking, Assets or the Knowledge base for an
installation that does not use them (a setting per organization; it hides menus and pages, the
API stays). Small, and keeps the app generic.

### C. Email (Resend)

One email service used everywhere, like `storage.py` for files:

- **`saumgm/email.py`** with a small interface (`send(to, subject, html, text, attachments)`)
  and backends chosen by `EMAIL_URL` in `.env`:
  - `resend://` with `RESEND_API_KEY=...` (your account),
  - `console://` for development: logs the message instead of sending (the default),
  - SMTP can be added later without touching the callers.
- **`EMAIL_FROM`** (for example `billing@yourdomain`, on a domain verified in Resend) and
  optional `EMAIL_REPLY_TO`.
- **Safety on the development PC:** the development database holds real client addresses.
  `EMAIL_REDIRECT_TO=you@example.com` sends every message to that address instead, with the
  real recipients noted at the top. Recommended on any non-production installation.
- **A log of every message** (`email_message` table): when, who sent it, to, subject, which
  record it belongs to (invoice, report, article), attachments, Resend's message id, sent or
  failed with the error. It shows on the record's History tab and under Admin → Email.
- **One "Send by email" dialog** in the frontend, reused on every screen: to / cc (filled from
  the contact's billing contact, or yourself for reports), subject and message from a template,
  the attachment listed. Templates per kind (invoice, receipt, report, article) are edited in
  Admin → Email, with placeholders such as `{invoice_number}`, `{client_name}`, `{total}`,
  `{due_date}`.
- **First uses in this step:** email an invoice (its stored PDF) and a payment receipt.
- Sending is synchronous (Resend answers in well under a second); a background queue comes with
  scheduled mail (document-expiry reminders, overdue reminders), which is a later step.

### D. Reports: income by payment date, PDF/print, email

**Income by payment date.** The sales-tax report already offers "by invoice date" (accrual) or
"by payment date" (cash). The sales report and profit & loss get the same choice:

- **By invoice date** (as now): an invoice counts in full in the period of its invoice date.
- **By payment date**: each payment counts in the period it was received, split over the
  invoice's lines in proportion (so the per-category breakdown still works), with the tax part
  separated out. Unpaid and written-off amounts never appear; a credit note counts when it is
  applied or refunded.
- The default comes from a business setting ("Report income by"), and each report screen can
  switch it. The choice is printed in the report heading and the CSV.
- Expenses stay by expense date. (With banking, "by paid date" for expenses becomes possible
  later.)

**PDF and print.** Every report gets a **PDF** button that produces a proper document (ReportLab,
like invoices): business name and logo, report title, period, basis, the table, totals, page
numbers, generated date. Printing is "open the PDF and print", which gives the same result in
every browser. The same PDF is what gets emailed.

**Email a report:** an **Email** button opens the dialog from C with the PDF attached, addressed
to yourself by default.

### E. Subscription packages

Today one subscription is one catalog item. In 2.0 a subscription is a **header with lines**:

- **Subscription** (header): client, what it is for (`service_identifier`, e.g. the domain),
  billing interval, start / next bill / end date, auto-renew, status, notes.
- **Subscription lines**: catalog item, description, quantity, price override, discount, and per
  line the vendor, vendor renewal date and unit cost (the domain renews at the registrar, the
  hosting elsewhere).
- The billing run makes **one invoice per subscription**, with one line per subscription line.
  (Subscriptions of one client due on the same day can be combined onto one invoice too: an
  option on the billing run.)
- **Packages** in the catalog: a named set of items with default prices (e.g. "Hosting + domain"),
  used to fill a new subscription's lines in one click. The lines stay editable per client.
  Optional for this step; easy to add afterwards.

**Data:** you said test subscriptions can be flushed. The migration can instead convert each
existing subscription into a header with one line, which loses nothing and costs little.
**(decide)** convert (recommended) or flush. Invoice lines already created by the billing run
keep their link to the subscription.

### F. Banking: accounts and registers

The goal: know the balance of each bank and credit-card account, and see every movement in and
out, without turning SauMGM into full double-entry accounting.

**Bank accounts.** A bank (a contact with the financial role) can have several accounts:

| Field | Notes |
|---|---|
| bank (contact) | the existing bank contacts |
| name | "Operating checking", "Amex Business" |
| kind | checking, savings, credit card, PayPal / other |
| number (last 4) | only the last digits are stored |
| opening balance and date | where the register starts |
| active | closed accounts stay for history |

**Register.** One list of transactions per account, like a checkbook:

| Field | Notes |
|---|---|
| date | |
| amount | positive = money in (deposit, refund), negative = money out (payment, charge). On a credit card, a charge increases what you owe |
| payee / description, reference (check no.) | free text |
| category | optional: an expense account, for reports |
| status | uncleared, cleared, reconciled |
| link (optional) | the deposit, expense, or the other side of a transfer |

Balances are **computed, never stored** (like payment status): current balance, cleared balance,
and a running balance in the register. For a credit card the screen shows "owed".

**What links, and what does not.** To keep this simple, only three links, each optional:

1. **Deposit → register:** recording a deposit on an account adds the matching register line
   (deposits get a bank account instead of only a bank contact).
2. **Expense → register:** an expense can say "paid from" an account (checking, or a card); that
   adds the register line. This covers bill pay: enter the bill as an expense, paid from checking.
3. **Transfer:** money from one account to another, as one action that writes both sides.
   **Paying the credit card** is a transfer from checking to the card account.

Everything else is a **free entry**: bank fees, interest, owner draws, odd items. A free entry
can have a category and can later be linked or converted into an expense. Changing a linked
expense or deposit updates its register line; deleting one removes it.

**Reconciling with a statement** (enter the statement's ending balance and date, tick the lines
that appear on it, the difference must be zero, then they become reconciled) is part of this
step if time allows, otherwise next. **Importing a bank's CSV or OFX file** is a later step.

**History (decide):** start each register at an opening balance on a chosen date (recommended:
the date you start using it), or also create register lines for older deposits and expenses.
Old Access data has no "paid from" information, so backfilling would be guesswork.

### G. Assets (CMDB, first step)

An inventory of equipment and licenses, built so that a fuller CMDB (relationships, configuration)
can grow from it later.

**Asset fields:**

| Field | Notes |
|---|---|
| asset tag | numbered like invoices (`A-0001`), or your own label |
| name | "Office NAS", "Jane's laptop" |
| category | editable list, see below |
| manufacturer, model, serial number | |
| status | in use, in stock, in repair, retired, disposed |
| owner | your business, or a client (see the decision below) |
| location, assigned to | free text to start |
| purchase date, price, vendor | vendor is a contact; optionally linked to the expense that paid for it |
| warranty expires, support contract ends | shown under "needs attention" like expiring documents |
| notes, attachments | receipts, photos, configs (existing file storage) |

**Categories** are an editable list in Admin, seeded with: Laptop, Desktop, Server, Monitor,
Network (router, switch, firewall, access point), Printer, Phone / tablet, Storage (NAS, disks),
Peripheral, Software license, Other. A category can define **extra fields** (text, number, date,
yes/no): for example CPU, RAM and OS for computers; license key, seats and renewal date for
software; IP address and MAC for network equipment. They are stored with the asset and searchable.

**Later, not in this step:** relationships between assets (this VM runs on that server, this
switch connects these), maintenance log, links to subscriptions (the hosting server behind a
client's subscription), network discovery or agents.

**(decide)** Is the inventory only for your own business's equipment, or also for equipment you
manage at clients? Recommended: allow both from the start (owner = any contact, defaulting to
your business); it costs one field now and is hard to add later.

### H. Knowledge base

A simple documentation hub: write articles in Markdown, find them by search, send them to clients.

- **Articles:** title, category, tags, body in Markdown, status (draft / published), and
  visibility: **internal** (only for you) or **shareable** (can be emailed to a client).
  Optionally linked to a contact ("how to set up email for Client X").
- **Categories:** an editable tree (e.g. Clients → Client X, How-to, Servers, Policies).
- **Editor:** a Markdown text area with a live preview side by side, plus a few buttons for
  headings, lists, links, code. Images and files can be attached and referenced in the text.
- **Search:** MariaDB full-text search over title, tags and body (works on 10.11), with the
  results ranked and the matching part shown. Filter by category, tag and visibility.
- **Sending:** "Email to..." on a shareable article sends it as a formatted email (Markdown
  converted to HTML), with a PDF copy attached optionally. Internal articles cannot be sent.
- **History:** every save is kept (who and when), with an older version viewable.

New dependencies: a Markdown renderer in the frontend (`react-markdown` with `remark-gfm`, MIT)
and in the backend for email and PDF (`markdown-it-py`, MIT). Rendered HTML is sanitized.

Later: public share links (a read-only page per article without login), client portal.

## 4. Decisions needed

| # | Question | Recommendation |
|---|---|---|
| 1 | A: drop `legacy_data` (JSON "Old system" tabs) together with the legacy tables? | keep it; it is small and holds the old notes |
| 2 | E: convert existing subscriptions to the new shape, or flush them? | convert |
| 3 | E: may the billing run combine several subscriptions of one client into one invoice? | yes, as an option |
| 4 | F: register history: opening balance on a start date, or backfill old deposits/expenses? | opening balance |
| 5 | F: statement reconciliation in the first banking step? | yes if it fits, otherwise next |
| 6 | G: assets for your business only, or for clients' equipment too? | both |
| 7 | H: public share links for articles now, or email only? | email only for now |
| 8 | C: which sender address (on a domain verified in Resend)? | e.g. `billing@` your domain |
| 9 | General: anything in this list more urgent than the order in section 2? | |
