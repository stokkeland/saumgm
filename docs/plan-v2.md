# SauMGM 2.0 plan

Status: **agreed in outline**, nothing built yet. The owner's decisions are recorded in
[section 4](#4-decisions).

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
   - [E. Subscriptions: what you bill and what you pay](#e-subscriptions-what-you-bill-and-what-you-pay)
   - [I. Reminders: to-do list, digest email, scheduled job](#i-reminders-to-do-list-digest-email-scheduled-job)
   - [F. Banking: accounts and registers](#f-banking-accounts-and-registers)
   - [G. Assets (CMDB, first step)](#g-assets-cmdb-first-step)
   - [H. Knowledge base](#h-knowledge-base)
4. [Decisions](#4-decisions)

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
| 5 | E. Subscriptions: client subscriptions with packages, vendor subscriptions | converts subscription data | M |
| 6 | I. Reminders: to-do list, digest email, `notify` command and timer | uses C and E | M |
| 7 | F. Banking | the biggest new area | L |
| 8 | G. Assets | new module | M |
| 9 | H. Knowledge base | new module, uses C | M |
| 10 | Release 2.0: `release/v2.0`, tag `v2.0.0`, upgrade the server | | S |

The order of 7–9 can change freely. Each module adds its own items to the reminders (I) as it
arrives: banking (accounts not reconciled), assets (warranties ending).

## 3. The parts

### A. Clean-up: legacy tables, SKU on invoices

**Legacy tables.** The database has 20 `legacy_*` tables (`legacy_tblinvoicehdr`, ...). They
are verbatim copies of the Access tables, written once by the importer; the application never
reads them. A migration drops them. Before it runs, `update.sh` makes a backup, and the original
`.mdb` and the 1.0 SQL export remain the reference.

What stays, because 1.0 data depends on it:

| Kept | Used for |
|---|---|
| `payment_allocation.legacy_sales_tax`, `legacy_taxable_amount` | cash-basis sales-tax report for old payments (Access stored tax per payment) |
| `invoice_line.legacy_unit_tax` | the tax column on old invoices |
| `legacy_id` columns | links back to the Access record numbers; harmless |
| `legacy_data` (JSON per contact, invoice, expense, ...) | the "Old system" tab; small, so kept |

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
routers and for the module's **reminder items** (see I). Adding a module then means adding a
folder and one line, without touching the shell.

**Admin section.** Settings, Users (moved out of Settings), Email settings, Audit log and About
(version, database version) move under `/admin`. Only owners see it, as with the audit log now;
bookkeepers keep read access where they have it today.

**Turning modules off.** Admin → Modules can hide Banking, Assets or the Knowledge base for an
installation that does not use them (a setting per organization; it hides menus and pages, the
API stays). Small, and keeps the app generic.

Built in part B: the module folders and registry, the grouped menu (sections fold; the
choice is remembered per browser) and the Admin section with Settings, Users, Audit log and
About. Switching modules off comes with the first module that can be switched off (F, Banking),
so Admin → Modules never shows an empty list.

### C. Email (Resend)

One email service used everywhere, like `storage.py` for files:

- **`saumgm/email.py`** with a small interface (`send(to, subject, html, text, attachments)`)
  and backends chosen by `EMAIL_URL` in `.env`:
  - `resend://` with `RESEND_API_KEY=...` (your account),
  - `console://` for development: logs the message instead of sending (the default),
  - SMTP can be added later without touching the callers.
- **Sender, configurable:** the from address and name, and an optional reply-to, are business
  settings in Admin → Email; `EMAIL_FROM` in `.env` is only the default until they are set. The
  address must be on a domain verified in Resend; a "Send test email" button checks the setup.
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
- Sending is synchronous (Resend answers in well under a second). Scheduled mail (the reminder
  digest) runs from a timer on the server, see I.

Built in part C as described, with these details: credit notes have their own template; the
API is generic (`/api/email/compose|send/{record_type}/{id}`), so reports (D) and articles (H)
add a record type rather than new endpoints; sent emails appear in the record's History as an
"email" event, and the full log is under Admin → Email (owner). The demo loader records a few
sent messages without sending anything.

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

Built in part D as described, with these details: there are no refund records yet, so by
payment date a credit note counts nowhere (it only lowers what is still owed); payment amounts
not applied to an invoice wait until they are; the profit & loss by payment date has no bad
debts (what was never received was never income). The upgrade sets "Report income by" to the
business's "Report tax by". Reports are emailed through their own endpoints
(`/api/reports/{report}/email`) rather than a record type, since a report is a query, not a
stored record; the message has its own template.

### E. Subscriptions: what you bill and what you pay

Recurring things come in two kinds that rarely line up one to one:

- **Client subscriptions**, what you **bill**: hosting, domains, support plans you sell. Some
  have a vendor behind them, some are only your own work.
- **Vendor subscriptions**, what you **pay**: the server you rent, domain registrations, software
  licenses, phone and internet. One server may carry many clients' hosting; some vendor costs
  belong to no client at all.

They become two separate lists with their own screens, due dates and reminders, joined only by
an optional link.

**Client subscriptions** (Sales → Subscriptions). In 1.0 a subscription is one catalog item; in
2.0 it is a **header with lines**, so hosting and a domain go on one invoice:

- **Header:** client, what it is for (`service_identifier`, e.g. the domain), billing interval,
  start / next bill / end date, auto-renew, status, notes.
- **Lines:** catalog item, description, quantity, price override, discount.
- The billing run makes **one invoice per subscription**, one invoice line per subscription
  line, and can optionally combine a client's subscriptions due on the same day into one invoice.
- **Packages** in the catalog: a named set of items with default prices ("Hosting + domain") that
  fills a new subscription's lines in one click; the lines stay editable per client.

**Vendor subscriptions** (Money → Vendor subscriptions; new):

| Field | Notes |
|---|---|
| vendor | a contact with the vendor role |
| name, what it is for | "VPS host-01", "example.com registration" |
| amount, interval | monthly, yearly, every N months |
| next due date, end date | |
| expense account | the category the cost is booked to |
| paid from | a bank or card account (once F exists); optional before that |
| autopay | charged automatically (a card on file) or paid by you; affects the reminder wording |
| auto-renew, status, notes | cancelled ones stay for history |

**Record payment** on a vendor subscription creates the expense (vendor, account, amount; once F
exists also the register line on the "paid from" account) and moves the next due date on by one
interval. Nothing else is created automatically.

**The optional link** "uses": a client subscription line can name the vendor subscription(s) it
depends on, many-to-many. It is information only, never billing logic:
- on a client subscription: the cost behind it and the margin;
- on a vendor subscription: which clients depend on it, before you cancel or let it lapse.

**Data:** existing subscriptions are **converted**: each becomes a header with one line. Where a
1.0 subscription has vendor details (vendor, vendor renewal date, unit cost), a vendor
subscription is created from them and linked. Invoice lines created by earlier billing runs keep
their link to the subscription.

Built in part E as described, with these details: the billing run makes one invoice per
subscription by default, and a checkbox combines a client's subscriptions due on the same day;
packages are under Catalog → Packages and "Add a package" appends their items to the lines; a
vendor subscription used by several client lines shares its cost equally between the active
ones (shown per month, with the margin); "paid from" waits for banking (F). The 1.0 unit cost
of a subscription without a vendor is kept in its notes.

### I. Reminders: to-do list, digest email, scheduled job

One place that answers "what needs doing", on screen and by email, with **billing clients and
paying bills kept apart**.

**The to-do list** (a page, and a summary on the dashboard), in sections:

| Section | Items | Default lead time |
|---|---|---|
| **Bill clients** | client subscriptions due for billing; button to the billing run | 14 days |
| **Pay vendors** | vendor subscriptions due; autopay ones marked "will be charged, check the account" | 10 days |
| **Collect** | overdue invoices | when overdue |
| **Documents** | contact documents expiring (the 1.0 `remind_days_before` setting) | per document |
| **Assets** | warranties and support contracts ending (with G) | 30 days |
| **Banking** | accounts not reconciled for a while (with F) | 35 days |

Lead times are business settings (Admin → Reminders). Each module provides its own section
through the module registry (B), so new modules join without changing this one.

**The digest email:** the same list, sent to the owners (or the addresses set in Admin →
Reminders), grouped by section, with links into the app. It says how long it has been since
anyone signed in, using the `last_login_at` the app already records, e.g. *"Nobody has signed in
for 20 days. 3 client subscriptions are due for billing within 14 days; 2 vendor payments are
due within 10 days."*

**The `notify` command** builds and sends the digest, for a timer or cron job:

```sh
cd /opt/saumgm/backend
sudo -u saumgm .venv/bin/python -m saumgm notify               # send if anything is due
sudo -u saumgm .venv/bin/python -m saumgm notify --dry-run     # print it, send nothing
sudo -u saumgm .venv/bin/python -m saumgm notify --json        # the data, for your own scripts
sudo -u saumgm .venv/bin/python -m saumgm notify --if-idle 20  # only if nobody signed in for 20 days
```

- It sends nothing when nothing is due (unless `--always`), so a daily schedule does not create
  noise.
- **Scheduling:** a systemd timer `saumgm-notify.timer` (daily at 07:00, plus the `@` template for
  several instances), installed like the backup timer. A plain cron line works too:
  `0 7 * * * cd /opt/saumgm/backend && sudo -u saumgm .venv/bin/python -m saumgm notify`.
- Every digest is logged as an email message (C), so Admin → Email shows what was sent when.

**From other machines, later:** read-only API tokens (Admin → API tokens) so a script elsewhere
can call `GET /api/reminders` with a token instead of a browser login. Not needed for the timer
on the server; a small step once someone needs it.

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
   adds the register line. This covers bill pay: enter the bill as an expense, paid from checking,
   or press "Record payment" on a vendor subscription (E), which does both.
3. **Transfer:** money from one account to another, as one action that writes both sides.
   **Paying the credit card** is a transfer from checking to the card account.

Everything else is a **free entry**: bank fees, interest, owner draws, odd items. A free entry
can have a category and can later be linked or converted into an expense. Changing a linked
expense or deposit updates its register line; deleting one removes it.

**Reconciling with a statement** (enter the statement's ending balance and date, tick the lines
that appear on it, the difference must be zero, then they become reconciled) is part of this
step if time allows, otherwise next. **Importing a bank's CSV or OFX file** is a later step.

**Starting point:** each register starts at an **opening balance on a start date you choose**
per account; older deposits and expenses are not copied in (the Access data does not say which
account paid what). To match history:
- add manual entries dated after the start date (e.g. set the start to the last statement you
  trust and enter the months since by hand);
- the start date and opening balance can be changed later, and the balances follow;
- a **balance adjustment** entry (marked as such) brings the register in line with a statement
  when the difference is not worth tracing.

Entries dated before the start date are refused, so the opening balance always means "the
balance on that day".

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

**Whose equipment:** both your own and equipment you manage at clients. The owner field is any
contact, defaulting to your business; the asset list filters by owner, and a client's page gets
an Assets tab.

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

## 4. Decisions

Decided by the owner:

| Part | Decision |
|---|---|
| E | Existing subscriptions are **converted**, not flushed. |
| E | Subscriptions are **two kinds**: client subscriptions (billed) and vendor subscriptions (paid), separate lists and reminders, joined by an optional information-only link. |
| F | Registers start at an **opening balance on a start date chosen per account**, with manual entries and balance adjustments to match history. |
| G | Assets cover **both** the business's own equipment and equipment managed at clients. |
| C | The **sender address is configurable** (business setting, `.env` default). |
| I | Added: reminders with separate "bill clients" and "pay vendors" sections, a digest email and a `notify` command for a timer or cron. |

Going ahead with the recommendation unless the owner says otherwise:

| Part | Question | Recommendation |
|---|---|---|
| A | Drop `legacy_data` (JSON "Old system" tabs) with the legacy tables? | keep it; it is small and holds the old notes |
| E | Billing run may combine a client's subscriptions due the same day into one invoice? | yes, as an option |
| F | Statement reconciliation in the first banking step? | yes if it fits, otherwise next |
| H | Public share links for articles now, or email only? | email only for now |
| I | API tokens for scripts on other machines now? | later; the `notify` command covers the server |
