"""Mapping the Access rows into the SauMGM schema (docs/design.md section 6).

Principles: keep old identifiers (file numbers, invoice numbers), never recalculate history,
and report data problems instead of silently fixing them.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from saumgm.legacy_import import convert as cv
from saumgm.legacy_import.config import ImportConfig
from saumgm.legacy_import.source import LegacyData, Row
from saumgm.models import (
    Account,
    AuditLog,
    CatalogItem,
    Deposit,
    DepositItem,
    Expense,
    ExpenseLine,
    Invoice,
    InvoiceLine,
    InvoiceTax,
    OrganizationAddress,
    Party,
    PartyAddress,
    PartyContact,
    PartyRole,
    Payment,
    PaymentAllocation,
    TaxExemption,
    TaxJurisdiction,
)
from saumgm.models.enums import (
    AccountType,
    AddressType,
    AuditActor,
    InvoiceStatus,
    PartyKind,
    PartyRoleType,
)
from saumgm.seed import create_organization, jurisdiction_code
from saumgm.services.archive import archive_through

FILE_TYPE_ROLES = {
    "B": PartyRoleType.SELF,
    "C": PartyRoleType.CLIENT,
    "V": PartyRoleType.VENDOR,
    "M": PartyRoleType.FINANCIAL,
    "R": PartyRoleType.RESOURCE,
    "F": PartyRoleType.TAX_AUTHORITY,
}

RECEIPT_MATCH_DAYS = 120
NATIVE_EXEMPTION = "Native American"


@dataclass
class ReceiptMatch:
    receipt_id: int
    payment_legacy_id: int
    how: str


@dataclass
class ImportResult:
    organization_id: int
    batch_id: str
    issues: list[str] = field(default_factory=list)
    receipt_matches: list[ReceiptMatch] = field(default_factory=list)
    unmatched_receipts: list[Row] = field(default_factory=list)
    orphan_deposit_items: list[Row] = field(default_factory=list)
    catalog_review: list[CatalogItem] = field(default_factory=list)
    unparsed_terms: dict[str, int] = field(default_factory=dict)
    archived: dict[str, int] = field(default_factory=dict)


def _datetime(value: Any) -> datetime | None:
    day = cv.to_date(value) if not isinstance(value, int) else cv.int_date(value)
    return datetime.combine(day, time()) if day else None


class AccessImporter:
    def __init__(self, session: Session, data: LegacyData, config: ImportConfig) -> None:
        self.session = session
        self.data = data
        self.config = config
        self.result = ImportResult(organization_id=0, batch_id=str(uuid.uuid4()))
        self.parties: dict[str, Party] = {}  # by file number
        self.client_parties: dict[int, Party] = {}  # by old ClientID
        self.accounts: dict[int, Account] = {}  # by old expAccountID
        self.catalog: dict[int, CatalogItem] = {}  # by old productID
        self.invoices: dict[int, Invoice] = {}  # by old InvoiceNo
        self.jurisdictions: dict[str, int] = {}

    def rows(self, table: str) -> list[Row]:
        return self.data[table].rows

    def issue(self, message: str) -> None:
        self.result.issues.append(message)

    def run(self) -> ImportResult:
        self.create_organization()
        self.import_parties()
        self.import_accounts()
        self.import_catalog()
        self.import_invoices()
        self.import_payments()
        self.import_deposits()
        self.import_expenses()
        if self.config.archive_through:
            self.result.archived = archive_through(
                self.session,
                self.org_id,
                self.config.archive_through,
                batch_id=self.result.batch_id,
            )
        self.session.add(
            AuditLog(
                organization_id=self.org_id,
                actor=AuditActor.SYSTEM,
                batch_id=self.result.batch_id,
                action="import",
                entity_type="organization",
                entity_id=str(self.org_id),
                changes={"source": "MS Access", "issues": len(self.result.issues)},
            )
        )
        self.session.flush()
        return self.result

    # -- organization -------------------------------------------------------------------------

    def create_organization(self) -> None:
        setup = self.config.organization
        setup.invoice_number_next = max(r["InvoiceNo"] for r in self.rows("tblInvoiceHdr")) + 1
        file_numbers = [int(n) for r in self.rows("tblFile") if (n := cv.pad_file_no(r["fileno"]))]
        setup.party_number_next = max(file_numbers) + 1
        org = create_organization(self.session, setup)
        self.org = org
        self.org_id = org.id
        self.result.organization_id = org.id
        for addr in self.config.addresses:
            self.session.add(OrganizationAddress(organization_id=org.id, **vars(addr)))
        self.jurisdictions = {
            j.code: j.id
            for j in self.session.query(TaxJurisdiction).filter_by(organization_id=org.id)
        }

    # -- parties ------------------------------------------------------------------------------

    def import_parties(self) -> None:
        clients = {cv.pad_file_no(c["FileNo"]): c for c in self.rows("tblClient")}
        vendors = {cv.pad_file_no(v["FileNo"]): v for v in self.rows("tblVendor")}

        for f in sorted(self.rows("tblFile"), key=lambda r: str(r["fileno"])):
            file_no = cv.pad_file_no(f["fileno"])
            assert file_no
            client = clients.pop(file_no, None)
            vendor = vendors.pop(file_no, None)
            party = self.build_party(f, file_no, client, vendor)
            self.session.add(party)
            self.parties[file_no] = party
            if client:
                self.client_parties[client["ClientID"]] = party
            if f["Type"] in {"C", "V"} and not (client or vendor):
                self.issue(
                    f"File {file_no} ({f['Name']}) is type {f['Type']} but has no "
                    f"{'client' if f['Type'] == 'C' else 'vendor'} record; imported without "
                    "address or contact details."
                )

        for file_no in list(clients) + list(vendors):
            self.issue(f"Client/vendor record for unknown file {file_no} was not imported.")

        self.session.flush()
        self_party = self.parties.get(self.config.self_party_no)
        if self_party is None:
            raise ValueError(f"self_party_no {self.config.self_party_no} not found in tblFile")
        if PartyRoleType.SELF not in {r.role for r in self_party.roles}:
            self_party.roles.append(PartyRole(role=PartyRoleType.SELF))
        self.org.self_party_id = self_party.id

    def build_party(self, f: Row, file_no: str, client: Row | None, vendor: Row | None) -> Party:
        company = cv.clean((client or {}).get("Company")) or cv.clean((vendor or {}).get("Company"))
        person = cv.clean((client or {}).get("Name"))
        file_name = cv.clean(f["Name"]) or file_no
        name = company or person or file_name
        closed = bool((client or {}).get("Closed")) or bool((vendor or {}).get("Closed"))
        details = client or vendor or {}

        legacy: dict[str, Any] = {"file_type": f["Type"]}
        if f["Inactive"] or closed:
            # Everyone starts active; the old flag is kept for the clean-up.
            legacy["inactive_in_old_system"] = True
        if file_name != name:
            legacy["file_name"] = file_name
        if cv.clean(f.get("FSdirectory")):
            legacy["fs_directory"] = f["FSdirectory"]
        if client:
            legacy["client"] = {"ClientID": client["ClientID"], "Nick": client["Nick"]}
        if vendor:
            legacy["vendor"] = {"VendorID": vendor["VendorID"], "Nick": vendor["Nick"]}

        party = Party(
            organization_id=self.org_id,
            party_no=file_no,
            short_code=cv.clean(f["nick"]) or file_no,
            name=name,
            kind=PartyKind.PERSON if client and not company and person else PartyKind.COMPANY,
            is_active=True,
            phone=cv.clean(details.get("Phone")),
            fax=cv.clean(details.get("Fax")),
            email=cv.clean(details.get("EMail") or details.get("Email")),
            website=cv.clean(details.get("url")),
            notes="\n\n".join(
                n
                for n in (
                    cv.clean((client or {}).get("Notes")),
                    cv.clean((vendor or {}).get("Notes")),
                )
                if n
            )
            or None,
            legacy_data=legacy,
        )
        created = _datetime(f["created"])
        if created:
            party.created_at = created

        roles = {FILE_TYPE_ROLES[f["Type"]]}
        if client:
            roles.add(PartyRoleType.CLIENT)
        if vendor:
            roles.add(PartyRoleType.VENDOR)
        party.roles = [PartyRole(role=role) for role in sorted(roles)]

        if any(cv.clean(details.get(k)) for k in ("Address1", "Address2", "City", "State", "Zip")):
            party.addresses.append(
                PartyAddress(
                    address_type=AddressType.BILLING,
                    is_default=True,
                    line1=cv.clean(details.get("Address1")),
                    line2=cv.clean(details.get("Address2")),
                    city=cv.clean(details.get("City")),
                    region=cv.clean(details.get("State")),
                    postal_code=cv.clean(details.get("Zip")),
                    country_code=cv.country_code(details.get("Country"), details.get("State")),
                )
            )
        if client and person and company:
            party.contacts.append(
                PartyContact(name=person, mobile=cv.clean(client.get("Cellular")), is_primary=True)
            )
        elif client and cv.clean(client.get("Cellular")):
            party.contacts.append(
                PartyContact(name=name, mobile=cv.clean(client["Cellular"]), is_primary=True)
            )
        if client and client.get("Native"):
            # "Native" marked Seneca / Native American clients, who are exempt from sales tax.
            party.tax_exemptions.append(
                TaxExemption(
                    certificate_type=NATIVE_EXEMPTION,
                    notes="Imported from the old system's Native flag.",
                )
            )
        if vendor and cv.clean(vendor.get("priContactName")):
            party.contacts.append(
                PartyContact(
                    name=vendor["priContactName"].strip(),
                    phone=cv.clean(vendor.get("priContactPhone")),
                    email=cv.clean(vendor.get("priContactEmail")),
                    is_primary=not party.contacts,
                )
            )
        return party

    # -- accounts and catalog -----------------------------------------------------------------

    def import_accounts(self) -> None:
        for a in self.rows("tblExpenseAccount"):
            account = Account(
                organization_id=self.org_id,
                code=str(a["expAccount"]),
                name=a["nick"].strip(),
                description=cv.clean(a["descr"]),
                account_type=AccountType.COGS if a["cogs"] else AccountType.EXPENSE,
                legacy_id=a["expAccountID"],
            )
            self.session.add(account)
            self.accounts[a["expAccountID"]] = account
        self.session.flush()

    def import_catalog(self) -> None:
        for p in sorted(self.rows("tblProduct"), key=lambda r: r["productID"]):
            unit = cv.clean(p["unit"])
            recurrable = bool(p["recurrable"])
            item = CatalogItem(
                organization_id=self.org_id,
                sku=cv.clean(p["sku"]),
                name=cv.clean(p["nick"]) or f"Product {p['productID']}",
                description=cv.clean(p["description"]),
                item_type=cv.guess_item_type(unit, recurrable),
                unit=unit,
                price=cv.dec0(p["price"]),
                default_discount_pct=cv.discount_pct(p["discount"]),
                billing_interval_months=cv.billing_interval(unit, recurrable, p["recurPeriod"]),
                unit_cost=cv.dec(p["cost_purchase"]),
                is_active=p["inactive_date"] is None,
                legacy_id=p["productID"],
                legacy_data={
                    key: cv.jsonable(p[key])
                    for key in (
                        "discount",
                        "recurrable",
                        "recurPeriod",
                        "last_purchase",
                        "update_date",
                        "inactive_date",
                    )
                },
            )
            created = _datetime(p["create_date"])
            if created:
                item.created_at = created
            self.session.add(item)
            self.catalog[p["productID"]] = item
            self.result.catalog_review.append(item)
        self.session.flush()

    # -- invoices -----------------------------------------------------------------------------

    def import_invoices(self) -> None:
        lines_by_invoice: dict[int, list[Row]] = defaultdict(list)
        for d in sorted(self.rows("tblInvoiceDtl"), key=lambda r: r["InvoiceDtlID"]):
            lines_by_invoice[d["Invoice"]].append(d)

        unparsed: dict[str, int] = defaultdict(int)
        for h in sorted(self.rows("tblInvoiceHdr"), key=lambda r: r["InvoiceNo"]):
            party = self.client_parties.get(h["Client"])
            if party is None:
                self.issue(f"Invoice {h['InvoiceNo']} has unknown client {h['Client']}; skipped.")
                continue
            issue_date = cv.to_date(h["InvDate"])
            terms_text = cv.clean(h["Terms"])
            terms_days = cv.parse_terms(terms_text)
            if terms_text and terms_days is None:
                unparsed[terms_text] += 1
            cancelled = h["Status"] == "Cancelled"
            tax_amount = cv.dec0(h["SalesTax"])
            jurisdiction_id = None
            state = (cv.clean(h["BillState"]) or "").upper()
            if tax_amount and state:
                jurisdiction_id = self.jurisdictions.get(jurisdiction_code("US", state))

            invoice = Invoice(
                organization_id=self.org_id,
                number=str(h["InvoiceNo"]),
                party_id=party.id,
                status=InvoiceStatus.VOID if cancelled else InvoiceStatus.ISSUED,
                issue_date=issue_date,
                terms_days=terms_days,
                terms_text=terms_text,
                due_date=(
                    issue_date + timedelta(days=terms_days)
                    if issue_date and terms_days is not None
                    else None
                ),
                bill_to_company=cv.clean(h["BillCompany"]),
                bill_to_name=cv.clean(h["BillName"]),
                bill_to_line1=cv.clean(h["BillAddress1"]),
                bill_to_line2=cv.clean(h["BillAddress2"]),
                bill_to_city=cv.clean(h["BillCity"]),
                bill_to_region=cv.clean(h["BillState"]),
                bill_to_postal_code=cv.clean(h["BillZip"]),
                bill_to_country=cv.clean(h["BillCountry"]),
                bill_to_phone=cv.clean(h["BillPhones"]),
                bill_to_email=cv.clean(h["email"]),
                tax_jurisdiction_id=jurisdiction_id,
                tax_location_text=cv.clean(h["SalesTaxLocation"]),
                freight=cv.dec0(h["Freight"]),
                adjustment=cv.dec0(h["Adjustment"]),
                adjustment_note=cv.clean(h["AdjustmentNote"]),
                notes=cv.clean(h["Notes"]),
                subtotal=cv.dec0(h["SubTotal"]),
                tax_total=tax_amount,
                total=cv.dec0(h["OriginallyDue"]),
                issued_at=_datetime(h["InvDate"]),
                void_reason="Cancelled in the old system" if cancelled else None,
                is_historical=True,
                legacy_id=h["InvoiceNo"],
                legacy_data={
                    "status": h["Status"],
                    "final": cv.jsonable(h["Final"]),
                    "bill_fax": cv.clean(h["BillFax"]),
                },
            )
            taxable_base = Decimal("0.0000")
            for order, d in enumerate(lines_by_invoice.pop(h["InvoiceNo"], [])):
                line = self.build_line(order, d)
                invoice.lines.append(line)
                if line.legacy_unit_tax:
                    taxable_base += line.line_total
            if tax_amount:
                invoice.taxes.append(
                    InvoiceTax(
                        jurisdiction_id=jurisdiction_id,
                        name=invoice.tax_location_text or self.org.tax_label,
                        rate=None,
                        taxable_base=taxable_base,
                        amount=tax_amount,
                    )
                )
            self.check_invoice_totals(h, invoice)
            self.session.add(invoice)
            self.invoices[h["InvoiceNo"]] = invoice

        for invoice_no, lines in lines_by_invoice.items():
            for d in lines:
                self.issue(
                    f"Invoice line {d['InvoiceDtlID']} belongs to unknown invoice {invoice_no}; "
                    f"not imported: {d['ItemDescr']!r}, {cv.dec0(d['ItemCost'])} x "
                    f"{cv.dec0(d['ItemQTY'])}."
                )
        self.result.unparsed_terms = dict(unparsed)
        self.session.flush()

    def build_line(self, order: int, d: Row) -> InvoiceLine:
        price = cv.dec0(d["ItemCost"])
        discount = cv.dec0(d["ItemDiscount"])
        quantity = cv.dec0(d["ItemQTY"])
        item = self.catalog.get(d["Product"])
        return InvoiceLine(
            sort_order=order,
            catalog_item_id=item.id if item else None,
            description=cv.clean(d["ItemDescr"]) or (item.name if item else ""),
            quantity=quantity,
            unit=cv.clean(d["ItemUnit"]),
            unit_price=price,
            unit_discount=discount,
            line_total=cv.line_total(price, discount, quantity),
            legacy_unit_tax=cv.dec(d["ItemTax"]),
            legacy_id=d["InvoiceDtlID"],
        )

    def check_invoice_totals(self, h: Row, invoice: Invoice) -> None:
        computed = invoice.subtotal + invoice.freight + invoice.adjustment + invoice.tax_total
        if abs(computed - invoice.total) > Decimal("0.01"):
            self.issue(
                f"Invoice {h['InvoiceNo']}: stored total {invoice.total} differs from subtotal + "
                f"freight + adjustment + tax = {computed}; stored value kept."
            )
        if invoice.total != invoice.total.quantize(Decimal("0.01")):
            self.issue(
                f"Invoice {h['InvoiceNo']}: total {invoice.total} has fractions of a cent; "
                "stored value kept."
            )

    # -- payments -----------------------------------------------------------------------------

    def import_payments(self) -> None:
        receipts = {r["trxID"]: r for r in self.rows("tblPaymentReceived")}
        payments: list[Payment] = []
        for p in sorted(self.rows("tblInvoicePayment"), key=lambda r: r["InvoicePaymntID"]):
            invoice = self.invoices.get(p["InvoiceNo"])
            if invoice is None:
                self.issue(
                    f"Payment {p['InvoicePaymntID']} for unknown invoice {p['InvoiceNo']} "
                    "was not imported."
                )
                continue
            if p["POT"] is None:
                self.issue(
                    f"Payment {p['InvoicePaymntID']} on invoice {p['InvoiceNo']} has no date; "
                    "imported without one."
                )
            amount = cv.dec0(p["Amount"])
            payment = Payment(
                organization_id=self.org_id,
                party_id=invoice.party_id,
                received_date=cv.to_date(p["POT"]),
                amount=amount,
                is_historical=True,
                legacy_id=p["InvoicePaymntID"],
            )
            payment.allocations.append(
                PaymentAllocation(
                    invoice_id=invoice.id,
                    amount=amount,
                    legacy_sales_tax=cv.dec(p["SalesTax"]),
                    legacy_taxable_amount=cv.dec(p["TaxableAmount"]),
                    legacy_id=p["InvoicePaymntID"],
                )
            )
            linked = receipts.pop(p["chargePaymentID"], None) if p["chargePaymentID"] else None
            if linked:
                self.apply_receipt(payment, linked, "linked in the old system")
            self.session.add(payment)
            payments.append(payment)

        invoice_numbers = {inv.id: no for no, inv in self.invoices.items()}
        unmatched = [p for p in payments if not p.legacy_data]
        for receipt in sorted(receipts.values(), key=lambda r: r["trxID"]):
            match = self.match_receipt(receipt, unmatched, invoice_numbers)
            if match is None:
                self.result.unmatched_receipts.append(receipt)
                continue
            unmatched.remove(match)
            self.apply_receipt(match, receipt, "matched by client, amount and date")
        self.session.flush()

    def match_receipt(
        self, receipt: Row, candidates: list[Payment], invoice_numbers: dict[int, int]
    ) -> Payment | None:
        party = self.parties.get(cv.pad_file_no(receipt["recFrom"]) or "")
        received = cv.to_date(receipt["recPOT"])
        amount = cv.dec0(receipt["payAmount"])
        if party is None or received is None:
            return None
        mentioned = {int(n) for n in re.findall(r"\b(\d{4})\b", receipt["payDescr"] or "")}
        best: tuple[int, int, Payment] | None = None
        for payment in candidates:
            if payment.party_id != party.id or payment.amount != amount:
                continue
            if payment.received_date is None:
                continue
            days = abs((payment.received_date - received).days)
            if days > RECEIPT_MATCH_DAYS:
                continue
            invoice_no = invoice_numbers[payment.allocations[0].invoice_id]
            rank = (0 if invoice_no in mentioned else 1, days)
            if best is None or rank < best[:2]:
                best = (*rank, payment)
        return best[2] if best else None

    def apply_receipt(self, payment: Payment, receipt: Row, how: str) -> None:
        description = cv.clean(receipt["payDescr"])
        payment.method = cv.METHODS.get((receipt["payMethod"] or "").strip().lower())
        payment.channel = cv.CHANNELS.get((receipt["recMethod"] or "").strip().lower())
        payment.reference = cv.check_number(description)
        payment.notes = description
        payment.legacy_data = {
            "receipt_id": receipt["trxID"],
            "receipt_date": cv.jsonable(receipt["recPOT"]),
            "receipt_match": how,
        }
        self.result.receipt_matches.append(
            ReceiptMatch(receipt["trxID"], payment.legacy_id or 0, how)
        )

    # -- deposits -----------------------------------------------------------------------------

    def import_deposits(self) -> None:
        deposits: dict[int, Deposit] = {}
        for h in sorted(self.rows("tblDepositHdr"), key=lambda r: r["depositID"]):
            if h["depositDate"] is None:
                self.issue(f"Deposit {h['depositID']} has no date; imported without one.")
            deposit = Deposit(
                organization_id=self.org_id,
                deposit_date=cv.to_date(h["depositDate"]),
                notes=cv.clean(h["depositNotes"]),
                legacy_id=h["depositID"],
            )
            self.session.add(deposit)
            deposits[h["depositID"]] = deposit
        for d in sorted(self.rows("tblDepositDtl"), key=lambda r: r["depositItemId"]):
            parent = deposits.get(d["depositId"])
            if parent is None:
                self.result.orphan_deposit_items.append(d)
                continue
            parent.items.append(
                DepositItem(
                    amount=cv.dec0(d["depAmount"]),
                    description=cv.clean(d["depDescr"]),
                    legacy_id=d["depositItemId"],
                )
            )
        self.session.flush()

    # -- expenses -----------------------------------------------------------------------------

    def import_expenses(self) -> None:
        lines_by_journal: dict[int, list[Row]] = defaultdict(list)
        for t in sorted(self.rows("tblExpenseTrx"), key=lambda r: r["expTrxID"]):
            lines_by_journal[t["ExpJorunalID"]].append(t)

        for j in sorted(self.rows("tblExpenseJournal"), key=lambda r: r["trxJournalID"]):
            legacy: dict[str, Any] = {}
            vendor = self.find_party(j["fileNo"], j, "vendor", legacy)
            for_party = self.find_party(j["refFileNo"], j, "for", legacy)
            expense = Expense(
                organization_id=self.org_id,
                expense_date=cv.to_date(j["trxDate"]),
                entered_date=cv.to_date(j["entryDate"]),
                vendor_party_id=vendor.id if vendor else None,
                for_party_id=for_party.id if for_party else None,
                reference=cv.clean(j["refInvNo"]),
                description=cv.clean(j["descr"]),
                legacy_id=j["trxJournalID"],
                legacy_data=legacy or None,
            )
            for order, t in enumerate(lines_by_journal.pop(j["trxJournalID"], [])):
                account = self.accounts.get(t["trxAccount"])
                if account is None:
                    self.issue(
                        f"Expense line {t['expTrxID']} has unknown account {t['trxAccount']}; "
                        "not imported."
                    )
                    continue
                expense.lines.append(
                    ExpenseLine(
                        account_id=account.id,
                        amount=cv.dec0(t["amount"]),
                        sort_order=order,
                        legacy_id=t["expTrxID"],
                    )
                )
            self.session.add(expense)

        for journal_id, lines in lines_by_journal.items():
            for t in lines:
                self.issue(
                    f"Expense line {t['expTrxID']} belongs to unknown journal entry {journal_id}; "
                    f"not imported: account {t['trxAccount']}, amount {cv.dec0(t['amount'])}."
                )
        self.session.flush()

    def find_party(self, raw: Any, j: Row, role: str, legacy: dict[str, Any]) -> Party | None:
        text = cv.clean(raw)
        if text is None:
            return None
        file_no = cv.pad_file_no(text)
        party = self.parties.get(file_no or "")
        if party is None:
            legacy[f"{role}_file_no"] = text
            self.issue(
                f"Expense {j['trxJournalID']} refers to unknown {role} file {text!r}; "
                "kept in legacy_data."
            )
        elif file_no != text:
            legacy[f"{role}_file_no"] = text
            self.issue(
                f"Expense {j['trxJournalID']}: {role} file number {text!r} read as {file_no} "
                f"({party.name})."
            )
        return party


def import_access(session: Session, data: LegacyData, config: ImportConfig) -> ImportResult:
    return AccessImporter(session, data, config).run()
