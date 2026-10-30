# SauMGM — Design

Status: **living design** — phases 1–5 are built (see §7). Mark up this file; code and this document should agree.

SauMGM is a small-business management system: contacts (clients, vendors, banks, tax authorities), a product/service catalog, client subscriptions, invoicing, payments, bank deposits, expenses, and sales tax. It replaces a 2004-era MS Access application and must carry all of its historical data forward. It is designed to be generic (open-sourceable): everything specific to one business is configuration or data, never code.

---

## 1. Goals and non-goals

**Goals**
- Re-create the useful parts of the Access app with a better workflow, not a screen-for-screen copy.
- Keep 100% of historical data, and prove it with a reconciliation report.
- Generic and configurable: business identity, currency, locale/number format, tax setup, terms, numbering.
- Runs today on a single Ubuntu 24.04 server behind Apache httpd; can be containerized and scaled later without code changes.
- Separate API backend and interactive JS frontend.
- Local user accounts now; SSO (Entra ID via OIDC or SAML) addable without schema changes.

**Non-goals (for v1)**
- Multi-currency (one configured currency per business).
- Multi-business UI (the schema supports it, the UI assumes one).
- Projects module (old data archived only; may be redesigned later).
- Emailing invoices (planned, post-v1).
- Full double-entry general ledger.

---

## 2. Architecture

```
Browser (React SPA) ──HTTPS/JSON──> API (Python, FastAPI) ──> MariaDB
                                          │
                                          └──> File storage (logos, receipts, invoice PDFs)
```

| Layer | Choice | Why |
|---|---|---|
| API | Python 3.13, FastAPI, Pydantic v2 | Typed, readable, auto-generated OpenAPI docs |
| ORM / migrations | SQLAlchemy 2.0, Alembic | Mature; versioned schema changes |
| Database | MariaDB 10.11+ (`utf8mb4`, InnoDB) | Ubuntu 24.04 package; cloud-managed options exist |
| PDF | ReportLab (Platypus) | Pure Python wheels on Windows and Linux; WeasyPrint was the first choice but needs GTK/Pango system libraries, awkward on Windows dev machines and in slim containers |
| Number/date formatting (server) | Babel | Locale-aware currency and dates in PDFs and exports |
| Frontend | React + TypeScript + Vite | Large ecosystem, good interactivity |
| UI kit | Mantine (forms, dates, tables, notifications, dark mode) | Rich business components without custom CSS work |
| Data fetching | TanStack Query; types generated from the API's OpenAPI schema | Frontend breaks at compile time if the API changes |
| Auth | Server-side sessions (HttpOnly cookie), argon2 passwords, Authlib (OIDC), python3-saml (SAML, later) | Safe for an SPA on the same origin |

**Twelve-factor rules** (so containerizing later is trivial):
- All deployment config from environment variables (`DATABASE_URL`, `SECRET_KEY`, `STORAGE_URL`, …); `.env` file locally, never committed.
- API is stateless; sessions in the DB (Redis optional later).
- Files go through a storage interface: local directory now, S3-compatible later.
- Logs to stdout; `/api/health` endpoint; schema changes only via Alembic.

**Hosting now (Ubuntu 24.04):** `gunicorn` + `uvicorn` workers under systemd; Apache serves the built SPA as static files and reverse-proxies `/api` (`mod_proxy`, `mod_headers`, TLS via certbot); nightly `mariadb-dump` backups plus the storage directory.

**Later:** two images (API, static frontend), `docker-compose.yml` with MariaDB for dev/self-hosters, then Kubernetes / Cloud Run / etc.

### Repository layout
```
backend/            FastAPI app, models, services, Alembic migrations, tests
frontend/           React app
backend/saumgm/legacy_import/  one-off Access → MariaDB importer + reconciliation
deploy/             Apache vhost, systemd units, later Dockerfiles/compose
docs/               this design, setup guides
tmp/                (git-ignored) local private files, e.g. the .mdb
```

### Development environment
- Dev machine: Windows 11, Python 3.13, local **MariaDB 13.0** (no Docker/WSL).
- Databases: `claudesaumgm` (dev; also holds the raw Access archive as `legacy_*` tables) and `test_claudesaumgm` (recreated by automated tests).
- Credentials live in `backend/.env` (git-ignored), never in code.
- Node.js 24 (LTS) for the frontend.
- Portability rules, because dev (Windows, MariaDB 13) differs from production (Linux):
  - All table and column names lowercase `snake_case` (Windows uses `lower_case_table_names=1`, Linux `0`).
  - **Production stays on MariaDB 10.11** (Ubuntu 24.04 package). Use nothing newer: no 11.x+ features or syntax. CI runs the test suite against `mariadb:10.11` to enforce this.
  - Production hardening: remove the default `test_%` grant to `PUBLIC` (`mariadb-secure-installation`).

### Database topology
- Now: a single MariaDB 10.11 server with backups (nightly `mariadb-dump`, plus binary logs if point-in-time recovery is wanted).
- Later: a Galera cluster across nodes/locations. Rules followed from day one so this needs no redesign:
  - InnoDB only; every table has an explicit primary key.
  - Never rely on `AUTO_INCREMENT` values being contiguous or ordered (Galera interleaves them per node). Invoice and party numbers come from counter rows updated inside the transaction, not from ids.
  - No `LOCK TABLES`, `GET_LOCK()` or XA transactions; keep transactions short. Writes that can conflict (number counters) are retried on deadlock/certification failure.
  - No `MyISAM`/`MEMORY` tables and no non-deterministic statements that depend on statement-based replication.

---

## 3. Configuration and localization

Two kinds of configuration:
1. **Deployment** (env vars): DB URL, secrets, storage location, allowed origins, SSO client secrets.
2. **Business** (database, edited in the app's Settings screen): the `organization` row and related tables.

`organization` (one row now; every business-owned table carries `organization_id`, filtered automatically by the data layer):

| Field | Example | Notes |
|---|---|---|
| legal_name, display_name | | What appears on documents |
| payable_to | "J.T. Stokkeland" | "Make checks payable to" line |
| self_party_id | → party 00010000 | The business is also a party (for expense "for whom" etc.) |
| addresses | remit-to, physical — with effective dates | Old invoices re-print with the address valid at the time |
| logo, tagline, footer text | | Stored via the file storage interface |
| country_code | `US` | ISO 3166-1 |
| currency_code | `USD` | ISO 4217; drives symbol and decimal places |
| locale | `en-US` | Number style (`1,234.56` vs `1 234,56` vs `1.234,56`), date order, used by frontend `Intl` and backend Babel |
| timezone | `America/New_York` | |
| date_format | locale default, overridable | |
| fiscal_year_start | `01-01` | For YTD and reports |
| tax_label | "Sales Tax" | "VAT", "GST/HST" in other countries |
| prices_include_tax | false | Future-proofing for VAT countries |
| default_terms_days | 30 | |
| invoice_number_next / prefix | 1369 / "" | Continues from the Access numbering |
| party_number_next / format | 00010170 / 8-digit | Continues the file-number scheme |

Money is stored as `DECIMAL(15,4)` (enough for any currency's minor units and unit prices with fractions); totals are rounded to the currency's minor units (2 for USD/CAD/EUR, 0 for JPY) using half-up rounding. Python uses `Decimal` throughout — never floats.

---

## 4. Data model

### 4.1 Parties (replaces tblFile, tblClient, tblVendor)
- `party` — `party_no` (unique, keeps the old file numbers, e.g. `00010162`), `short_code` (old "nick", unique), `name`, `kind` (company/person), `notes`, `active`, `created_at`, `legacy_*` ids.
- `party_role` — client, vendor, bank/financial, tax_authority, resource, self. A party may hold several roles (fixes the one-type-per-file limit).
- `party_address` — type (billing, service/ship-to, remit), lines, city, region (state/province), postal code, country, `is_default`. The service address drives the sales-tax location.
- `party_contact` — person name, title, phone(s), email, primary flag.
- Client-specific: default terms; tax exemptions via `tax_exemption` (below).
- Vendor-specific: account number with vendor, default expense account.

### 4.2 Catalog (replaces tblProduct; expanded for services)
- `catalog_item`
  - `sku`, `name`, `description`
  - `item_type`: **goods**, **service_hourly**, **service_fixed**, **subscription**
  - `unit` (ea, hour, month, year, foot, license…)
  - `price` (default unit price), `default_discount_pct`
  - `tax_category_id`
  - `revenue_category_id` — new: groups sales for reporting (Hosting, Domains, Development, Consulting, Hardware, Software…)
  - subscription defaults: `billing_interval` (1, 3, 6, 12 months), `billing_timing` (in advance / in arrears)
  - cost side: `default_vendor_id`, `unit_cost`, `cogs_account_id` — for resold items (domains, hosting, certificates), so margin can be reported
  - `active`, `created_at`, `updated_at`
- `catalog_price` — price history with effective dates. *Deferred: not in the v1 schema.*
- `revenue_category` — small editable list.
- Cleanup: all old products are imported; unused ones are marked inactive; a merge tool lets you fold duplicates together without breaking historical invoice lines.

### 4.3 Subscriptions: client (billed) and vendor (paid)
- `subscription` (client subscription, what is billed)
  - `party_id` (client), `service_identifier` — what this subscription is *for*: a domain name, hosting account, server name, contract number
  - `billing_interval_months`, `start_date`, `next_bill_date`, `end_date`, `auto_renew`
  - `status`: active, paused, cancelled
  - `notes`
- `subscription_line` — `catalog_item_id`, `description` (copied from the item, editable), `quantity`, `price_override`, `discount_pct` (client-specific pricing), `sort_order`. Hosting and a domain go on one subscription and one invoice.
- `vendor_subscription` (what is paid: a rented server, a domain registration, a license, phone and internet) — `party_id` (vendor), `name`, `service_identifier`, `amount`, `interval_months`, `next_due_date`, `end_date`, `expense_account_id`, `autopay` (charged automatically; changes only how reminders read), `auto_renew`, `status`, `notes`. **Record payment** makes an expense (vendor, account, amount; `expense.vendor_subscription_id` links it) and moves `next_due_date` on by one interval; nothing else is automatic.
- `subscription_use` — a client subscription line uses a vendor subscription (many-to-many). Information only, never billing logic: the client subscription shows its cost share and margin per month (a vendor subscription used by several active lines is split equally between them); the vendor subscription lists who depends on it.
- `catalog_package` / `catalog_package_item` — a named set of items with default quantity, price and discount ("Hosting + domain") that fills a new subscription's lines; the lines stay editable, and changing the package later leaves subscriptions alone.
- **Pricing**: each billing period bills, per line, `quantity` × unit price (the line's override or the catalog price); periods are billed in advance unless the line's catalog item says arrears.
- **Billing run**: "Generate invoices for subscriptions due through date X" → one **draft** invoice per subscription (or, as an option, one per client for its subscriptions due on the same day), a line per subscription line with the period in the description (e.g. `Hosting - example.com (2026-11-01 to 2027-10-31)`), then `next_bill_date` advances. You review and issue drafts manually.
- **Views**: upcoming renewals (dashboard), client subscriptions (Sales), vendor subscriptions with their next due dates (Money), packages (Catalog).
- **From 1.0**: each subscription became a header with one line; its vendor details (vendor, vendor renewal date, unit cost) became a linked vendor subscription.
- **Import aid**: the importer proposes subscriptions from recent recurring invoice lines (same client + recurring product within the last ~13 months) as a review list — not created automatically.

### 4.4 Invoices (replaces tblInvoiceHdr / tblInvoiceDtl)
- `invoice`
  - `number` (assigned when issued; drafts have none), `party_id`
  - `status`: draft, issued, void — *paid / partially paid / overdue are computed* from allocations and `due_date`
  - `issue_date`, `terms_days`, `due_date`
  - bill-to snapshot (name, company, address, email) — copied at issue time like the old app, so history doesn't change when a client moves
  - `tax_location_jurisdiction_id` (defaults from the client's service address)
  - `freight`, `adjustment`, `adjustment_note`, `notes`
  - stored totals: `subtotal`, `tax_total`, `total` (recomputed for drafts; frozen at issue)
  - `pdf_file_id` (rendered at issue), `is_historical` (imported, locked as-is)
- `invoice_line` — `catalog_item_id`, `subscription_id` (nullable), `description`, `quantity`, `unit`, `unit_price`, `unit_discount` (amount; UI accepts % or amount), `tax_category_id`, `line_total`, `revenue_category_id`, `sort_order`.
- `invoice_tax` — per-jurisdiction tax snapshot: jurisdiction, rate name, rate, taxable base, amount.
- Credit notes: `invoice` with `kind = credit_note` referencing the original — for discounts, refunds and write-offs given after the fact.
- **Editing issued invoices (revisions)** — mistakes can be corrected directly:
  - Any issued invoice, including imported historical ones, can be edited with **Revise**. A reason is required.
  - Before the change is saved, the complete invoice (header, bill-to snapshot, lines, tax rows, totals) is copied into `invoice_revision` (`invoice_id`, `revision_no`, `snapshot` JSON, `reason`, `changed_by`, `changed_at`). The invoice's `revision_no` increments.
  - The PDF is re-rendered; every earlier PDF is kept and linked to its revision, so you can always see exactly what the client was sent.
  - The invoice page shows a *History* tab with each revision and a field-by-field diff.
  - Guard rails (warnings, not blocks): the new total is lower than payments already applied (→ suggests leaving the overpayment as client credit); the invoice falls in a sales-tax period marked as filed; the PDF has already been sent.
  - The invoice number never changes. Void remains for invoices that should not exist at all.
  - A setting can restrict revising to the owner role.

- **Write-offs (bad debt)** — an issued invoice the client will never pay can be written off (one at a time or many from the list), with a reason and a date. `write_off_date`, `write_off_amount` (the balance at that moment) and `write_off_reason` are stored on the invoice; its payment status becomes *written off*, the balance due becomes zero and it no longer counts as receivable or overdue. The sale itself is unchanged. A written-off invoice cannot be revised or voided; *undo write-off* (owner, with a reason) reopens it if the client pays after all. Reports show the write-off as a bad-debt expense and its tax share as a sales-tax credit.
- **Documents** — issuing renders the invoice PDF (`saumgm/documents.py`) and keeps it (`pdf_file_id`); revising keeps the previous PDF on the revision and stores a new one, so the document as sent is always available. Drafts and imported invoices are rendered on request. Receipts and deposit slips are rendered on request. The letterhead uses the business logo (Admin → Settings → Business), the remit-to address valid on the invoice date and the invoice footer text; amounts and dates use the business locale (Babel).
- Implementation notes: totals are rounded to the currency's minor units (2 for USD) and always returned with 4 decimals in JSON; an invoice counts as settled when within half a cent of its total (old totals had fractions of a cent); credit notes are numbered `CN-1`, `CN-2`, ...; imported invoices keep their stored tax when revised.

### 4.5 Payments and deposits (replaces tblInvoicePayment, tblPaymentReceived, tblDeposit*)
- `payment` — `party_id`, `received_date`, `method` (check, cash, card, bank transfer, PayPal, …), `channel` (mail, in person, electronic), `reference` (check no.), `amount`, `notes`, `deposit_id` (nullable = undeposited funds).
- `payment_allocation` — `payment_id`, `invoice_id`, `amount`. One payment can cover several invoices; one invoice can have several payments.
- `deposit` — `bank_party_id`, `bank_account_id` (2.0: the account it went into, see §4.14), `deposit_date`, `notes`; `deposit_item` for non-payment items (rare; old data has some).
- Flow: **Receive payment** (pick client → open invoices listed → allocate oldest first, adjustable) → payment waits in **Undeposited funds** → **Make deposit** (tick payments) → print deposit slip.

### 4.6 Expenses (replaces tblExpenseJournal / tblExpenseTrx / tblExpenseAccount)
- `account` — `code` (4010…), `name`, `description`, `type` (expense, cogs, later revenue), `active`. Keeps the existing chart of accounts.
- `expense` — `date`, `entered_at`, `vendor_party_id`, `for_party_id` (defaults to self; a client means billable/re-chargeable), `reference` (vendor invoice no.), `description`, attachments.
- `expense_line` — `account_id`, `amount`, optional `description`.
- Quick-entry form with vendor autocomplete, split lines, receipt upload (PDF/photo).

### 4.7 Sales tax (redesigned)
| Table | Purpose |
|---|---|
| `tax_jurisdiction` | Tree: country → state/province → county → city/locality, with `code` and optional filing/reporting code. Seeded with all US states + DC and all Canadian provinces/territories; lower levels added as needed. |
| `tax_rate` | Jurisdiction, name (NY State, Cattaraugus County, GST, HST, PST, QST…), rate, `effective_from`/`effective_to`. Rates are entered by the user, never hard-coded. |
| `tax_registration` | Where the business is registered to collect (registration number, filing frequency, first month of the filing year — New York's sales-tax quarters start in March). **Tax is only charged in registered jurisdictions.** Registrations for the same jurisdiction may not overlap in time. |
| `tax_filing` | A filing period marked as filed (period start/end, filed on, amount paid, reference). Revising an invoice dated in a filed period gives a warning. |
| `tax_category` | Taxability classes for catalog items: tangible goods, prewritten software, hosting/digital services, labor/professional services, non-taxable… |
| `taxability_rule` | Jurisdiction × category → taxable yes/no (inherits down the tree; overridable at lower levels). |
| `tax_exemption` | Per client (optionally per jurisdiction): certificate type and number, valid from/to, uploaded copy. |

**Calculation** (pluggable `TaxEngine` interface; built-in table engine for v1, `saumgm/services/tax_engine.py`):
1. Resolve the invoice's tax location → the chain of jurisdictions (e.g. US → NY → Cattaraugus → Salamanca).
2. Skip jurisdictions the business isn't registered in; skip entirely if the client has a valid exemption.
3. For each line, use its tax category to decide taxable or not per jurisdiction.
4. Sum the taxable base per jurisdiction rate, multiply, and round per jurisdiction to the currency's minor units.
5. Store the result as `invoice_tax` rows (snapshot).

Defaults chosen while building: a line with no tax category, or a category without any rule up the tree, is taxable; freight and adjustments are not taxed; new organizations get a "Non-taxable" rule at country level.

**Filing periods**: monthly, quarterly or annual, counted from the registration's first month (`saumgm/services/tax_periods.py`); Admin → Settings → Sales tax lists each year's periods and whether they are filed.

**Reporting** (`saumgm/services/reports.py`): sales tax by jurisdiction for any date range or filing period — gross sales, non-taxable, taxable, tax collected, bad-debt credit and net tax due (shaped like NY ST-100/ST-101). Basis is a setting that the report can override:
- *Invoice date (accrual)*: tax on invoices issued in the period (credit notes subtract), less the tax share of invoices written off in the period.
- *Payment date (cash; what the old app did)*: each payment's share of its invoice's sales, taxable sales and tax. Imported payments use the tax the old system recorded on them.

*Which items are taxable in which jurisdiction is a business/accounting decision — the app makes it configurable; confirm the rules with an accountant.*

### 4.8 Users and security
- `app_user` (name, email, active, last_login), `user_identity` (provider: local | oidc | saml, issuer, subject, password hash for local), `user_role` (user × organization × role: owner, bookkeeper, viewer — a fixed list, so no separate role table), `auth_session` (only the SHA-256 of the session token is stored).
- Local: argon2 password hashing, optional TOTP 2FA, login rate limiting.
- SSO: OIDC first (Authlib; Entra ID, Google, Keycloak…); SAML via python3-saml later. Identities link to existing users by email on first SSO login (admin-confirmable).
- CSRF protection on cookie-authenticated requests; strict CORS.
### 4.9 Audit log (everything)
- Every insert, update and delete on business tables is recorded automatically by a SQLAlchemy session hook, so no feature can forget to log:
  `audit_log` — `id`, `occurred_at`, `user_id`, `action` (create/update/delete/login/logout/login_failed/export/issue/void/revise/settings_change), `entity_type`, `entity_id`, `changes` (JSON: field → [old, new]), `reason` (when the action asks for one), `request_id`, `ip_address`, `user_agent`.
- Imports and billing runs log as a system actor, with a batch id.
- Append-only: the application never updates or deletes audit rows. Optional hardening: a separate DB user that can only `INSERT`/`SELECT` on `audit_log`.
- UI: a *History* tab on every record (contact, invoice, payment, expense, setting) and a global, filterable audit log (Admin → Audit log) for the owner role; CSV export.
- Retention: keep forever by default (volume is small); a setting allows archiving entries older than N years.

### 4.10 Files and storage
- Metadata in the DB: `stored_file` — `id`, `storage_key`, original name, content type, size, SHA-256 checksum, uploaded_by, created_at. Used for logos, receipts, exemption certificates and issued-invoice PDFs (one per revision).
- Content goes through a small storage interface (`put`, `get`, `delete`, `exists`, optional `signed_url`). Records only ever store the `storage_key` — never a path — so the backend can be swapped by configuration:
  - `file://` — local directory (dev; single server).
  - `s3://` — any S3-compatible service: AWS S3, Google Cloud Storage (S3 interop), Cloudflare R2, Backblaze B2, Wasabi, or self-hosted Garage / SeaweedFS / Ceph.
  - `azure://` — Azure Blob Storage (native SDK; fits an Entra ID shop).
- Keys are content-neutral and stable (`{org_id}/{yyyy}/{mm}/{uuid}`); objects are immutable (a new revision is a new object), which makes replication and caching simple.
- Files are served through the API (permission check + audit), or via short-lived signed URLs for cloud backends.
- Migrating between backends: one `saumgm storage migrate --to <url>` command copies every object (or `rclone sync`), verifies checksums, then the config is switched. No database changes.
- Replication/survivability options, smallest step first:
  1. Single server, `file://` + nightly encrypted offsite backup with restic (to B2/S3/another server). Covers disaster recovery, not uptime.
  2. Self-hosted, replicated object storage on Ubuntu: **Garage** (lightweight, S3-compatible, built for multi-site geo-distribution on small servers) — start with one node, add nodes in other locations later; the app just uses `s3://`. SeaweedFS is an alternative; Ceph is overkill at this size.
  3. Cloud object storage (S3/Azure Blob/GCS) with built-in cross-region replication.
  The database needs the same treatment for multi-region (MariaDB replication or Galera, or a managed service) — files and DB should be planned together.
- Storing files as DB BLOBs was considered: simplest (one backup, replicates with the DB) but bloats backups and doesn't fit cloud scaling; rejected in favour of the interface above.

### 4.12 Contact documents (W-9s, certificates, contracts)
- `party_document` — `party_id`, `document_type` (W-9, W-8, tax exemption certificate, certificate of insurance, contract, other), `title`, `file_id` (optional: a paper copy can be recorded and a scan attached later), `document_date` (signed/issued), `expires_on`, `remind_days_before` (default 30), `tax_exemption_id` (the exemption a certificate supports), `notes`, `archived_at`.
- Status is computed, never stored: no expiry / valid / expiring (inside the reminder window) / expired. Archived = replaced by a newer document; kept on file but no longer checked. Adding a W-9, W-8, insurance or exemption certificate offers to archive the current one of that type.
- The tax exemption (§4.7) stays the rule the tax engine uses; the certificate document is its evidence. Deleting an exemption keeps the certificate, unlinked.
- Files can contain taxpayer ids (a sole proprietor's W-9 has an SSN): viewers see the list but cannot open files (also not through `/api/files/{id}`), every download is written to the audit log, and responses are sent `Cache-Control: no-store`. Deleting a document is owner-only and meant for mistakes.
- `GET /api/documents/attention` lists current documents that have expired or are inside their reminder window; they are the Documents section of the to-do list (§4.13).

### 4.13 Reminders: the to-do list and the digest
- `services/reminders.py` builds the to-do list from sections, one provider each in `SECTIONS` (a new module adds its own, as it adds its router): **Bill clients** (client subscriptions due for billing within `organization.remind_bill_days`, default 14, plus draft invoices waiting to be issued; links to the billing run), **Pay vendors** (vendor subscriptions due within `remind_pay_days`, default 10; autopay ones say "will be charged, check the account"), **Collect** (overdue invoices), **Documents** (expired or inside each document's reminder window). Billing clients and paying vendors stay separate sections. Banking (F) and assets (G) add theirs.
- Each item has a title, date, amount, note, a flag (overdue, autopay, expired, expiring) and a link into the app. Shown on the To do page (`/todo`), shortened on the dashboard; `GET /api/reminders`.
- **Digest email** (`EmailKind.DIGEST`): the same list grouped by section, opening with how long it has been since anyone signed in (`app_user.last_login_at`) and one sentence per section. Links need `APP_URL`. It goes to `organization.remind_to`, or else every active owner; Admin → Reminders sets the lead times and recipients, previews it and sends it now. It is logged like every email.
- **`python -m saumgm notify`** sends it if anything is due (`--always`, `--dry-run`, `--json`, `--if-idle DAYS`, `--organization-id`), from the `saumgm-notify.timer` (daily 07:00; `@` template for instances). Nothing is remembered between runs: each day's digest is the current list.

### 4.14 Banking: accounts, registers, reconciliation
- `bank_account` — `party_id` (the bank contact), `name` (unique), `kind` (checking, savings, credit card, other: PayPal, cash), `number_last4` (only the last digits), `opening_date` and `opening_balance` (where the register starts: the balance on that day), `is_active` (closed accounts stay), `notes`.
- `bank_entry` — one register line: `entry_date`, signed `amount` (positive = money in; on a card a charge is negative, so a negative card balance is what is owed), `payee`, `description`, `reference` (check no.), `account_id` (optional category from the chart of accounts), `status` (uncleared, cleared, reconciled), `kind` (manual, deposit, expense, transfer, adjustment) and at most one link: `deposit_id`, `expense_id` (both unique), or `transfer_entry_id` (the other side; each side points at the other). Lines dated before the account's start are refused.
- **Three things write lines on their own** (services/banking.py): a deposit with `bank_account_id` (its total), an expense with `paid_from_account_id` (minus its total; payee from the vendor; category when it has a single account), and a **transfer** (both sides at once; paying the card is a transfer to its account). Changing the deposit or expense changes its line; clearing the account or deleting it removes the line. The line itself only changes its status; a transfer side changes both sides. Everything else is a **free entry**; a free line going out can be **made an expense** paid from that account (the line stays, linked). Free entries do not count in the reports until they are made expenses.
- Vendor subscriptions have `paid_from_account_id`; Record payment uses it unless told otherwise, so the expense lands in that register.
- Balances are computed, never stored: balance (all lines), cleared (cleared and reconciled), reconciled, and a running balance per line in register order (date, then entry order).
- `bank_reconciliation` — `statement_date`, `statement_balance`, who and when. **Reconciling**: the ticked lines plus everything reconciled before must come to the statement's ending balance (within half a cent); they become reconciled. A reconciled line is locked: it, and the deposit or expense behind it, cannot change amount, date or account, nor be deleted; the start date and opening balance cannot change while reconciliations exist. The owner can undo the latest reconciliation (its lines go back to cleared). A **balance adjustment** entry covers a difference not worth tracing.
- The to-do list's **Banking** section lists open accounts whose last reconciled statement (or start) is older than `organization.remind_reconcile_days` (default 35).
- Later: importing the bank's CSV or OFX file.

### 4.15 Assets (a first step toward a CMDB)
- `asset` — `tag` (unique; numbered `A-0001` by the `asset` number sequence unless given), `name`, `category_id`, `manufacturer`, `model`, `serial_number`, `status` (in use, in stock, in repair, retired, disposed), `owner_party_id` (the business itself by default, or a client whose equipment is managed; a contact's page has an Assets tab), `location`, `assigned_to` (free text for now), `purchase_date`, `purchase_price`, `vendor_party_id`, `expense_id` (the expense that paid for it), `warranty_expires`, `support_ends`, `notes`, `attributes` (JSON: the category's extra fields).
- `asset_category` — an editable list (Admin → Asset categories; owner), seeded for every business: Laptop, Desktop, Server, Monitor, Network, Printer, Phone / tablet, Storage, Peripheral, Software license, Other. `fields` defines extra fields `{key, label, type}` (text, number, date, yes/no), e.g. CPU, RAM and OS for computers, license key, seats and renewal date for software, IP and MAC address for network equipment. Values are checked against the fields when saved; changing an asset's category keeps the values of fields both categories have. The search covers the extra fields too.
- `asset_attachment` — receipts, photos, configuration backups (file storage). Viewers cannot open them (configurations can hold passwords), as with contact documents.
- Deleting an asset is owner-only and meant for mistakes; equipment sold or scrapped is marked disposed. Retired and disposed assets are not checked for warranties.
- The to-do list's **Assets** section: warranties and support contracts of assets in use, in stock or in repair that end within `organization.remind_asset_days` (default 30) or ended within as many days.
- Later: relationships between assets, a maintenance log, links to subscriptions (the server behind a client's hosting), discovery or agents.

### 4.16 Knowledge base
- `kb_article` — `title`, `category_id`, `tags` (lower case, comma-separated; the API speaks lists), `body` (Markdown, MEDIUMTEXT), `status` (draft, published), `visibility` (**internal**: only for the business; **shareable**: can be emailed to a client once published), `party_id` (the contact it is about; a contact's page has an Articles tab), `version` (the number of the latest saved version), created and updated by.
- `kb_category` — a tree (`parent_id`) of any depth, edited by owners and bookkeepers (Knowledge base → Categories); listing a category includes the articles below it. Nothing is seeded. A category with articles or subcategories cannot be deleted.
- `kb_article_version` — every save that changes the title, tags or text is kept in full (who, when); the Versions tab shows an older one and can restore it (as a new version). A save names the version it was made on (`base_version`) and is refused if someone saved a newer one meanwhile. The audit log records that the text changed, with its length, without copying it.
- `kb_attachment` — images and files kept with an article; the text refers to them by their download address, `![name](/api/files/12)`. The editor's "Attach a file" adds that reference at the cursor. Viewers can read articles and open their files (unlike asset and contact files).
- **Search:** every word must be in the title, tags or text (as part of a word, so short words such as "IP" and numbers like 10.0.0.1 are found); results are ranked by words in the title, then by MariaDB's full-text relevance (`FULLTEXT` index on title, tags and body), then by the latest change. Each result shows the part of the text around the first match. Filters: category (with the ones below it), tag, status, visibility, contact.
- **Markdown** is CommonMark with tables and strikethrough, the same in the browser (`react-markdown` with `remark-gfm`) and on the server (`markdown-it-py`, saumgm/markup.py). Raw HTML in the text is shown as text, never used, and unsafe link addresses are dropped.
- **Email and PDF:** "Email to…" on a published, shareable article sends the message (template `article`, Admin → Email), then the article as HTML, to the contact it is about. Images attached to the article go inline (`cid:`), other attached files it links go along as attachments, and links elsewhere in the app point to `APP_URL` (or are left out). A file the text points to that is not the article's own is never sent or printed. A PDF copy can be attached; the PDF (`/api/kb/articles/{id}/pdf`) has the logo, the title and the text with the article's images.
- Deleting an article (owner) deletes its versions and files.
- Later: public share links (a read-only page per article without login), a client portal.

### 4.11 Archiving
- Invoices, payments, deposits and expenses have `archived_at` (NULL = current). Archived records stay in their tables, keep all links, and count in every report; they are only hidden from everyday lists.
- Lists default to current records, with a "show archived" toggle (and an `include_archived` / `archived_only` filter on the API). Archived records open read-only; unarchiving is allowed for the owner role.
- `archive_through(cutoff)` (`saumgm/services/archive.py`) archives everything dated on or before a day; drafts are never archived; an undated payment follows its invoices. Each run writes one audit entry with the counts.
- Contacts (parties) have `archived_at` too, next to `is_active` ("inactive" = no longer used for new work; "archived" = hidden from lists). All imported contacts start active and unarchived; the old system's inactive/closed flag is kept in `legacy_data.inactive_in_old_system` for the clean-up. Catalog items use their active/inactive flag.
- The initial import archived everything dated 2016 or earlier.

---

## 5. Screens (v1)

- **Dashboard** — open receivables, overdue, YTD sales vs expenses, upcoming subscription renewals, the to-do list (shortened), tax due this period.
- **To do** — what needs doing, by section (§4.13); Admin → Reminders for lead times and the digest.
- **Contacts** — searchable list with role filters; contact page with addresses, people, subscriptions, invoices, payments, expenses, balance.
- **Catalog** — items by type, inactive toggle, merge duplicates.
- **Subscriptions** — client subscriptions with lines and packages, the billing run; vendor subscriptions with payments.
- **Invoices** — list (default: unpaid, not archived), editor (line entry with catalog search, live totals and tax), issue/void/credit note, PDF.
- **Payments** — receive payment, undeposited funds, deposits + slip (deposited to a bank account).
- **Assets** — equipment and licenses (own and clients'), with categories, extra fields and files (§4.15).
- **Knowledge base** — articles in Markdown with a live preview, a category tree, search, versions, files, PDF and email to clients (§4.16).
- **Bank accounts** — accounts with balances (cards show what is owed), each with its register, transfers and reconciling (§4.14).
- **Expenses** — list by period/account/vendor, quick entry with receipts.
- **Reports** — sales by month/client/revenue category, sales tax (by date range or filing period, accrual or cash), expenses by account/vendor/month, profit & loss (with cost of goods and bad debts), receivables aging. Sales and profit & loss count income by invoice date or by payment date (`organization.income_basis`, switchable per report): by payment date, each payment counts when received, without its tax share, spread over the invoice's lines for the category view; unpaid and written-off amounts never count, and credit notes do not count until refunds are recorded. Each report is built once as a `ReportDocument` (documents.py) and comes out as CSV, as a PDF (letterhead, period, basis, page numbers, generated time) or by email with that PDF; downloads and emails are audited. Invoice PDFs, receipts and deposit slips open from their pages. The invoice list with its filters covers the "invoice listing".
- **Settings** — business profile and locale, tax setup, terms, numbering, accounts, users.

Interaction expectations: archived records hidden unless "show archived" is on, global search, sortable/filterable tables, keyboard-friendly forms, inline validation, unsaved-changes warnings, light/dark mode.

---

## 6. Legacy migration (Access → MariaDB)

**Principles**: nothing is lost; old identifiers survive; history is not recalculated.

1. **Raw archive** — every Access table (including projects and all lookup tables) is copied verbatim into `legacy_<table>` tables in the application database (ignored by Alembic; each gets a surrogate `_row_id` primary key). Read-only, for audit. Keep the original `.mdb` in backups as well.
2. **Mapped import** — `python -m saumgm.legacy_import` reads the `.mdb` with pyodbc + the Microsoft Access ODBC driver (Windows), maps it into the new schema in one transaction, and carries `legacy_id` / `legacy_data` (unmapped fields as JSON). Re-runnable with `--reset`. Business details not in the `.mdb` (names, addresses) come from a TOML config.
3. **Reconciliation report** — row counts per entity; invoice totals, tax and payments per year; expenses per account per year; must match Access to the cent before the import is accepted.

| Access | New | Notes |
|---|---|---|
| tblFile | party (+ party_role from Type B/C/V/M/R/F) | fileno → party_no; nick → short_code; B (00010000) → self |
| tblClient / tblVendor | party_address, party_contact, role data | integer pseudo-dates (`20040808`, `0`) → real dates or null |
| tblProduct | catalog_item | `discount` is a price multiplier (1 = none, 0.95 = 5% off) → `default_discount_pct`; `recurrable`/`recurPeriod` → subscription fields |
| tblInvoiceHdr | invoice (`is_historical = true`, status issued/void) | Stored SubTotal/SalesTax/OriginallyDue kept exactly; Status "Cancelled" → void; free-text Terms → `terms_days` where parsable, original text kept in notes |
| tblInvoiceDtl | invoice_line | `ItemDiscount` is a per-unit discount **amount** (line = (cost − discount) × qty); `ItemTax` is per-unit tax |
| SalesTax + SalesTaxLocation | invoice_tax (one row, jurisdiction best-matched, e.g. "Salamanca NY") | |
| tblInvoicePayment | payment + payment_allocation (1:1, `is_historical`) | Tax/taxable amounts preserved on the allocation for historical tax reports; imported payments never show as undeposited |
| tblPaymentReceived | merged into the matching payment (method, channel, check no., notes) | Linked by `chargePaymentID`, else matched by client + amount + date (±120 days, invoice number in the text preferred). Unmatched receipts — donations credited to the dropped project accounts — stay in the archive and are listed in the report |
| tblDepositHdr / Dtl | deposit / deposit_item | Detail rows without a deposit stay in the archive only and are listed in the report |
| tblExpenseAccount | account | |
| tblExpenseJournal / Trx | expense / expense_line | `refFileNo` → `for_party_id`; `refInvNo` → reference |
| tblProject*, lookupProjectItemType, lookupInvoicableChoice | archive only | |

Known data issues are reported, not silently fixed: 3 client/vendor files without detail records, 1 payment and 1 deposit without a date (imported without one; dates are required only for new entries), 1 invoice whose total ≠ its components, 10 fractional-cent totals, 2 expense file numbers missing leading zeros (`10068` → `00010068`), 1 invoice line and 1 expense line without a parent.

**Result of the first real import (2026-10-20):** 535 of 535 reconciliation checks match; 3,434 rows archived.

---

## 7. Phases

1. **Foundation** ✅ — repo layout, backend skeleton (FastAPI, settings, DB session, Alembic, health endpoint, request-id logging), frontend skeleton (Vite + React + TS + Mantine + TanStack Query + typed API client), CI (ruff, mypy, pytest on MariaDB 10.11; oxlint + build).
2. **Schema + import** ✅ — 34-table schema for §4 (initial Alembic migration), seed data (US states + DC + PR, Canadian provinces/territories, starter tax categories, number sequences), raw archive, mapped import, reconciliation report; importer tested in CI with a synthetic dataset. *Exit met: reconciliation 535/535.*
3. **API** ✅ — 69 endpoints, 100 tests (interactive docs at `/api/docs`):
   - Auth: local accounts, server-side sessions in an HttpOnly cookie, double-submit CSRF token, throttled failed logins; roles owner / bookkeeper / viewer; `python -m saumgm create-user`.
   - Automatic audit hook on every ORM flush (field-level changes, user, request id, IP, parent record for child rows); History endpoint per record; audit log + CSV export for the owner.
   - Contacts, catalog, categories, accounts, settings, users, tax setup, invoices + credit notes + revisions, payments, deposits, expenses, subscriptions + billing run, archiving.
   - Smoke-tested on the imported data: every list responds in under 100 ms.
4. **Frontend** ✅ — React + Mantine screens for everything in §5: login and account, dashboard, contacts, invoices (editor with live server-side totals and tax, issue / revise / credit note / void, revision viewer), payments (apply to open invoices), deposits, expenses, subscriptions with the billing run, catalog, settings (business, addresses, sales tax, accounts, categories, numbering, users), audit log; history timeline on every record. Verified with Playwright end-to-end tests against a copy of the imported data (`frontend/e2e/`).
5. **Documents + reports** ✅ — file storage interface (`saumgm/storage.py`, `file://` backend), business logo upload (and importer option), ReportLab PDFs for invoices (kept as issued and per revision), receipts and deposit slips; write-offs for uncollectible invoices; sales-tax filing periods; reports API + screen with CSV downloads (sales, sales tax, expenses, profit & loss, aging). 119 backend tests, 17 end-to-end tests.
6. **Deploy** — install guide [docs/deploy/ubuntu.md](deploy/ubuntu.md) and `deploy/` (prerequisite check/install script, systemd unit, Apache vhost, nightly backup timer, update script, database export for MariaDB 10.11); then install on the Ubuntu server and cut over from Access.
7. **Post-v1** — email invoices, SSO (OIDC → SAML), Docker images/compose, recurring auto-issue, project module redesign.
8. **2.0** (in progress on `main`; 1.0 is on `release/v1.0`) — banking, email, report PDFs and income by payment date, subscriptions with lines, packages and vendor subscriptions, assets, knowledge base, modular layout: see [plan-v2.md](plan-v2.md).

---

## 7a. License, demo data, several instances

- **License:** GPL-3.0-or-later, copyright J. Thomas Stokkeland, <https://www.saumgm.com/>. Every source file carries the header (`tools/license_headers.py` adds it; CI fails without it). Dependencies keep their own licenses, all GPL-compatible, listed in `THIRD-PARTY-NOTICES.md` (generated by `tools/third_party_notices.py`). Note: the GPL does not oblige someone who runs a modified SauMGM as a web service to share their changes; the AGPL would. Kept as GPL by choice.
- **Demo data:** `python -m saumgm load-demo` (`saumgm/demo.py`) builds a fictional business through the app's own services (billing run, issue, revise, credit note, void, write-off, payments, deposits), dated relative to the load day, with generated PDFs for documents and receipts. A loader rather than an SQL file: stored files would be missing from a dump, dates would go stale, and the loader follows schema changes.
- **Several instances on one server:** a naming convention (`/opt/saumgm-NAME`, database `saumgm_NAME`, user `saumgm-NAME`, port in `/etc/saumgm/NAME.env`), systemd template units `saumgm@.service` and `saumgm-backup@.timer`, an Apache template, and `--instance NAME` for the install, backup and update scripts; see `docs/deploy/multiple-instances.md`.

## 8. Open items
- Client "Native" flag (21 clients) and "ActiveBilling" date: meaning to confirm; kept in `legacy_data` until then.
- Organization addresses: confirm which remit-to address is current and the dates each was valid; confirm the time zone.
- Production storage backend (local + restic to start, or Garage from day one).
- NY sales-tax setup: which localities you deliver to (filing frequency: annual, starting in March).
- Revenue categories and tax categories: starting lists to be drafted from the current product list.
