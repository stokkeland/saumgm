# SauMGM — Design

Status: **draft for review** — nothing is built yet. Mark up this file; it is the source of truth until the first code lands.

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
| PDF | WeasyPrint (HTML/CSS → PDF), Jinja2 templates | Invoice layout is themable per installation |
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

### Repository layout (proposed)
```
backend/            FastAPI app, models, services, Alembic migrations, tests
frontend/           React app
tools/import_access/  one-off Access → MariaDB importer + reconciliation
deploy/             Apache vhost, systemd units, later Dockerfiles/compose
docs/               this design, setup guides
tmp/                (git-ignored) local private files, e.g. the .mdb
```

### Development environment
- No Docker/WSL on the dev machine: develop against a **remote MariaDB** (dev database on the Ubuntu server), reached through an SSH tunnel rather than opening port 3306.
- Needed on the server: databases `saumgm_dev` and `saumgm_test`, plus `saumgm_legacy` for the archive; a user with full rights on those three only (migrations need CREATE/ALTER/DROP; tests recreate `saumgm_test`).
- Credentials live in `backend/.env` (git-ignored), not in chat or code.
- Install Node.js LTS on Windows for the frontend (`winget install OpenJS.NodeJS.LTS`).

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
- Client-specific: default terms, `tax_exempt` via `tax_exemption` (below), `active_billing_since`.
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
- `catalog_price` — price history with effective dates (optional in v1; keeps old prices visible).
- `revenue_category` — small editable list.
- Cleanup: all old products are imported; unused ones are marked inactive; a merge tool lets you fold duplicates together without breaking historical invoice lines.

### 4.3 Client subscriptions (new)
- `subscription`
  - `party_id` (client), `catalog_item_id`, `quantity`
  - `price_override`, `discount_pct` (client-specific pricing)
  - `service_identifier` — what this subscription is *for*: a domain name, hosting account, server name, contract number
  - `billing_interval`, `start_date`, `next_bill_date`, `end_date`, `auto_renew`
  - `status`: active, paused, cancelled
  - `vendor_party_id`, `vendor_renewal_date`, `unit_cost` — e.g. the registrar and the renewal date there, so upcoming vendor renewals and margin are visible
  - `notes`
- **Billing run**: "Generate invoices for subscriptions due through date X" → one **draft** invoice per client, a line per subscription with the period in the description (e.g. `example.com — 2026-11-01 to 2027-10-31`), then `next_bill_date` advances. You review and issue drafts manually.
- **Views**: upcoming renewals (next 30/60/90 days), per-client subscription list on the contact page, vendor renewals due.
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
- Credit notes: `invoice` with `kind = credit_note` referencing the original (corrections after issue, instead of editing).

### 4.5 Payments and deposits (replaces tblInvoicePayment, tblPaymentReceived, tblDeposit*)
- `payment` — `party_id`, `received_date`, `method` (check, cash, card, bank transfer, PayPal, …), `channel` (mail, in person, electronic), `reference` (check no.), `amount`, `notes`, `deposit_id` (nullable = undeposited funds).
- `payment_allocation` — `payment_id`, `invoice_id`, `amount`. One payment can cover several invoices; one invoice can have several payments.
- `deposit` — `bank_party_id`, `deposit_date`, `notes`; `deposit_item` for non-payment items (rare; old data has some).
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
| `tax_registration` | Where the business is registered to collect (registration number, filing frequency). **Tax is only charged in registered jurisdictions.** |
| `tax_category` | Taxability classes for catalog items: tangible goods, prewritten software, hosting/digital services, labor/professional services, non-taxable… |
| `taxability_rule` | Jurisdiction × category → taxable yes/no (inherits down the tree; overridable at lower levels). |
| `tax_exemption` | Per client (optionally per jurisdiction): certificate type and number, valid from/to, uploaded copy. |

**Calculation** (pluggable `TaxEngine` interface; built-in table engine for v1):
1. Resolve the invoice's tax location → the chain of jurisdictions (e.g. US → NY → Cattaraugus → Salamanca).
2. Skip jurisdictions the business isn't registered in; skip entirely if the client has a valid exemption.
3. For each line, use its tax category to decide taxable or not per jurisdiction.
4. Sum the taxable base per jurisdiction rate, multiply, and round per jurisdiction to the currency's minor units.
5. Store the result as `invoice_tax` rows (snapshot).

**Reporting**: sales tax by jurisdiction and period — gross sales, non-taxable, exempt, taxable, tax collected (shaped like NY ST-100/ST-101). Basis is a setting: invoice date (accrual) or payment date (cash; what the old app did).

*Which items are taxable in which jurisdiction is a business/accounting decision — the app makes it configurable; confirm the rules with an accountant.*

### 4.8 Users and security
- `user` (name, email, active, last_login), `user_identity` (provider: local | oidc | saml, subject, password hash for local), `role` + `user_role` (owner, bookkeeper, viewer), `session`.
- Local: argon2 password hashing, optional TOTP 2FA, login rate limiting.
- SSO: OIDC first (Authlib; Entra ID, Google, Keycloak…); SAML via python3-saml later. Identities link to existing users by email on first SSO login (admin-confirmable).
- CSRF protection on cookie-authenticated requests; strict CORS.
- `audit_log`: who, when, entity, before/after (JSON).

### 4.9 Files
`stored_file` — storage key, original name, content type, size, uploaded_by. Used for logos, receipts, exemption certificates, issued-invoice PDFs.

---

## 5. Screens (v1)

- **Dashboard** — open receivables, overdue, YTD sales vs expenses, upcoming subscription renewals, tax due this period.
- **Contacts** — searchable list with role filters; contact page with addresses, people, subscriptions, invoices, payments, expenses, balance.
- **Catalog** — items by type, inactive toggle, merge duplicates.
- **Subscriptions** — list, upcoming renewals, billing run.
- **Invoices** — list (default: unpaid), editor (line entry with catalog search, live totals and tax), issue/void/credit note, PDF.
- **Payments** — receive payment, undeposited funds, deposits + slip.
- **Expenses** — list by period/account/vendor, quick entry with receipts.
- **Reports** — invoice listing, sales by period/client/revenue category, sales tax, expenses by account/vendor/summary, receivables aging; all exportable to CSV/PDF.
- **Settings** — business profile and locale, tax setup, terms, numbering, accounts, users.

Interaction expectations: global search, sortable/filterable tables, keyboard-friendly forms, inline validation, unsaved-changes warnings, light/dark mode.

---

## 6. Legacy migration (Access → MariaDB)

**Principles**: nothing is lost; old identifiers survive; history is not recalculated.

1. **Raw archive** — every Access table (including projects and all lookup tables) is copied verbatim into `saumgm_legacy`. Read-only, for audit.
2. **Mapped import** — idempotent script (`tools/import_access`) reads the `.mdb` with pyodbc + the Microsoft Access ODBC driver (Windows), cleans and maps into the new schema, carrying `legacy_id` columns.
3. **Reconciliation report** — row counts per entity; invoice totals, tax and payments per year; expenses per account per year; must match Access to the cent before the import is accepted.

| Access | New | Notes |
|---|---|---|
| tblFile | party (+ party_role from Type B/C/V/M/R/F) | fileno → party_no; nick → short_code; B (00010000) → self |
| tblClient / tblVendor | party_address, party_contact, role data | integer pseudo-dates (`20040808`, `0`) → real dates or null |
| tblProduct | catalog_item | `discount` is a price multiplier (1 = none, 0.95 = 5% off) → `default_discount_pct`; `recurrable`/`recurPeriod` → subscription fields |
| tblInvoiceHdr | invoice (`is_historical = true`, status issued/void) | Stored SubTotal/SalesTax/OriginallyDue kept exactly; Status "Cancelled" → void; free-text Terms → `terms_days` where parsable, original text kept in notes |
| tblInvoiceDtl | invoice_line | `ItemDiscount` is a per-unit discount **amount** (line = (cost − discount) × qty); `ItemTax` is per-unit tax |
| SalesTax + SalesTaxLocation | invoice_tax (one row, jurisdiction best-matched, e.g. "Salamanca NY") | |
| tblInvoicePayment + tblPaymentReceived | payment + payment_allocation | `chargePaymentID = 0` → no link; tax/taxable amounts preserved for historical tax reports |
| tblDepositHdr / Dtl | deposit / deposit_item | 7 orphaned detail rows kept, flagged for review |
| tblExpenseAccount | account | |
| tblExpenseJournal / Trx | expense / expense_line | `refFileNo` → `for_party_id`; `refInvNo` → reference |
| tblProject*, lookupProjectItemType, lookupInvoicableChoice | archive only | |

Known data issues to report (not silently fix): 2 expense entries with unknown file numbers, 3 client/vendor files without detail records, 1 payment without a date, 1 invoice whose total ≠ components, fractional-cent totals.

---

## 7. Phases

1. **Foundation** — repo layout, backend skeleton, config/settings, Alembic, CI (lint, type-check, tests), dev DB connection.
2. **Schema + import** — models for §4, raw archive, mapped import, reconciliation report. *Exit: reconciliation passes.*
3. **API** — auth (local), contacts, catalog, subscriptions, invoices (with tax engine), payments, deposits, expenses, settings.
4. **Frontend** — app shell, login, screens in §5.
5. **Documents + reports** — invoice/receipt/deposit-slip PDFs, reports, CSV export.
6. **Deploy** — Apache vhost, systemd, TLS, backups on the Ubuntu server; cut over from Access.
7. **Post-v1** — email invoices, SSO (OIDC → SAML), Docker images/compose, recurring auto-issue, project module redesign.

---

## 8. Open items
- MariaDB dev/test/legacy databases and a user on the Ubuntu server (credentials into `backend/.env`).
- Install Node.js LTS on the dev machine.
- NY sales-tax setup: which localities you deliver to, and your filing frequency.
- Revenue categories and tax categories: starting lists to be drafted from the current product list.
- License choice for open-sourcing (e.g. MIT, Apache-2.0, AGPL-3.0).
