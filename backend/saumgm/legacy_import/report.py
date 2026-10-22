"""Markdown report of an import run. It contains business data: keep it out of git."""

from datetime import datetime

from saumgm.legacy_import import convert as cv
from saumgm.legacy_import.mapping import ImportResult
from saumgm.legacy_import.reconcile import Check


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", " ")


def render_report(
    result: ImportResult, checks: list[Check], archive_counts: dict[str, int], source: str
) -> str:
    failed = [c for c in checks if not c.ok]
    out = [
        "# Access import report",
        "",
        f"- Source: `{source}`",
        f"- Run: {datetime.now():%Y-%m-%d %H:%M}, batch `{result.batch_id}`",
        f"- Organization id: {result.organization_id}",
        f"- Reconciliation: **{'PASSED' if not failed else 'FAILED'}** "
        f"({len(checks) - len(failed)} of {len(checks)} checks match)",
        "",
    ]

    if failed:
        out += ["## Mismatches", "", "| Check | Access | New | ", "|---|---:|---:|"]
        out += [f"| {_cell(c.name)} | {c.expected} | {c.actual} |" for c in failed]
        out.append("")

    out += ["## Reconciliation", "", "| Check | Access | New | OK |", "|---|---:|---:|:-:|"]
    out += [
        f"| {_cell(c.name)} | {c.expected} | {c.actual} | {'✓' if c.ok else '✗'} |" for c in checks
    ]

    if result.archived:
        out += ["", "## Archived after import", ""]
        out += [f"- {kind}: {count}" for kind, count in result.archived.items()]

    out += ["", "## Data issues (imported as-is, review)", ""]
    out += [f"- {_cell(issue)}" for issue in result.issues] or ["- none"]

    out += [
        "",
        "## Deposit lines without a deposit (archive only, not imported)",
        "",
        "| Item id | Amount | Description |",
        "|---:|---:|---|",
    ]
    out += [
        f"| {d['depositItemId']} | {cv.dec0(d['depAmount'])} | {_cell(d['depDescr'] or '')} |"
        for d in result.orphan_deposit_items
    ]

    out += [
        "",
        f"## Receipts merged into payments ({len(result.receipt_matches)})",
        "",
        "| Receipt | Payment | How |",
        "|---:|---:|---|",
    ]
    out += [f"| {m.receipt_id} | {m.payment_legacy_id} | {m.how} |" for m in result.receipt_matches]

    out += [
        "",
        f"## Receipts not matched to an invoice payment ({len(result.unmatched_receipts)})",
        "",
        "Kept in the archive table `legacy_tblpaymentreceived`; mostly donations credited to",
        "project accounts, which are not migrated.",
        "",
        "| Receipt | From | Date | Amount | Description |",
        "|---:|---|---|---:|---|",
    ]
    out += [
        f"| {r['trxID']} | {r['recFrom']} | {cv.to_date(r['recPOT'])} | "
        f"{cv.dec0(r['payAmount'])} | {_cell(r['payDescr'] or '')[:120]} |"
        for r in result.unmatched_receipts
    ]

    out += [
        "",
        "## Terms that could not be converted to a number of days",
        "",
        "Kept as text on the invoice; no due date computed.",
        "",
    ]
    out += [f"- `{text}` ({count})" for text, count in result.unparsed_terms.items()] or ["- none"]

    out += [
        "",
        "## Catalog items to review",
        "",
        "Item type and billing interval were guessed from the old unit/recurring fields.",
        "",
        "| SKU | Name | Unit | Type | Interval (months) | Price | Discount % | Active |",
        "|---|---|---|---|---:|---:|---:|:-:|",
    ]
    out += [
        f"| {_cell(i.sku or '')} | {_cell(i.name)} | {_cell(i.unit or '')} | {i.item_type.value} "
        f"| {i.billing_interval_months or ''} | {i.price} | {i.default_discount_pct} "
        f"| {'yes' if i.is_active else 'no'} |"
        for i in result.catalog_review
    ]

    out += ["", "## Archive tables", "", "| Table | Rows |", "|---|---:|"]
    out += [f"| `{name}` | {count} |" for name, count in sorted(archive_counts.items())]
    out.append("")
    return "\n".join(out)
