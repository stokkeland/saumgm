"""Sales tax calculation (docs/design.md 4.7).

The built-in engine works from the configuration tables. Rules:

1. The invoice's tax location is a jurisdiction; its chain runs up to the country
   (e.g. Salamanca -> Cattaraugus County -> New York -> United States).
2. A jurisdiction's rates apply only if the business is registered there or in a jurisdiction
   above it (a New York registration covers NY's county and city rates).
3. A client exemption covers its jurisdiction and everything below it; an exemption without a
   jurisdiction covers everything.
4. Whether a line is taxable in a jurisdiction comes from the nearest taxability rule for the
   line's tax category, looking up the chain. Without a rule (or a category) a line is taxable.
5. For each rate in force on the invoice date: tax = taxable base x rate, rounded once per rate.

Freight and adjustments are not taxed. Another engine (e.g. a tax service) can replace this one
by implementing the same `calculate` signature.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from saumgm.models import (
    TaxabilityRule,
    TaxExemption,
    TaxJurisdiction,
    TaxRate,
    TaxRegistration,
)
from saumgm.services.money import ZERO, round_money


@dataclass(frozen=True)
class TaxableLine:
    amount: Decimal
    tax_category_id: int | None


@dataclass(frozen=True)
class TaxAmount:
    jurisdiction_id: int
    name: str
    rate: Decimal
    taxable_base: Decimal
    amount: Decimal


class TaxEngine(Protocol):
    def calculate(
        self,
        session: Session,
        *,
        organization_id: int,
        currency: str,
        jurisdiction_id: int | None,
        on_date: date,
        party_id: int | None,
        lines: Sequence[TaxableLine],
    ) -> list[TaxAmount]: ...


def _in_force(start: date | None, end: date | None, on_date: date) -> bool:
    return (start is None or start <= on_date) and (end is None or on_date <= end)


def jurisdiction_chain(session: Session, jurisdiction_id: int) -> list[TaxJurisdiction]:
    """The jurisdiction and its ancestors, from the country down."""
    chain: list[TaxJurisdiction] = []
    current = session.get(TaxJurisdiction, jurisdiction_id)
    while current is not None:
        chain.append(current)
        current = session.get(TaxJurisdiction, current.parent_id) if current.parent_id else None
    return list(reversed(chain))


class TableTaxEngine:
    def calculate(
        self,
        session: Session,
        *,
        organization_id: int,
        currency: str,
        jurisdiction_id: int | None,
        on_date: date,
        party_id: int | None,
        lines: Sequence[TaxableLine],
    ) -> list[TaxAmount]:
        if jurisdiction_id is None or not lines:
            return []
        chain = jurisdiction_chain(session, jurisdiction_id)
        if not chain or chain[0].organization_id != organization_id:
            return []
        ids = [j.id for j in chain]

        registrations = session.scalars(
            select(TaxRegistration).where(
                TaxRegistration.organization_id == organization_id,
                TaxRegistration.jurisdiction_id.in_(ids),
            )
        ).all()
        registered = {
            r.jurisdiction_id
            for r in registrations
            if _in_force(r.effective_from, r.effective_to, on_date)
        }
        if not registered:
            return []

        exempt_everywhere = False
        exempt: set[int] = set()
        if party_id is not None:
            exemptions = session.scalars(
                select(TaxExemption).where(
                    TaxExemption.party_id == party_id,
                    or_(
                        TaxExemption.jurisdiction_id.is_(None),
                        TaxExemption.jurisdiction_id.in_(ids),
                    ),
                )
            ).all()
            for e in exemptions:
                if _in_force(e.valid_from, e.valid_to, on_date):
                    if e.jurisdiction_id is None:
                        exempt_everywhere = True
                    else:
                        exempt.add(e.jurisdiction_id)
        if exempt_everywhere:
            return []

        rules = {
            (r.jurisdiction_id, r.tax_category_id): r.is_taxable
            for r in session.scalars(
                select(TaxabilityRule).where(TaxabilityRule.jurisdiction_id.in_(ids))
            )
        }

        def taxable(level: int, category_id: int | None) -> bool:
            if category_id is None:
                return True
            for j in reversed(chain[: level + 1]):  # nearest rule first
                rule = rules.get((j.id, category_id))
                if rule is not None:
                    return rule
            return True

        results: list[TaxAmount] = []
        covered = False  # registered here or above
        under_exemption = False
        for level, jurisdiction in enumerate(chain):
            covered = covered or jurisdiction.id in registered
            under_exemption = under_exemption or jurisdiction.id in exempt
            if not covered or under_exemption:
                continue
            base = sum(
                (line.amount for line in lines if taxable(level, line.tax_category_id)), ZERO
            )
            if not base:
                continue
            rates = session.scalars(
                select(TaxRate)
                .where(TaxRate.jurisdiction_id == jurisdiction.id)
                .order_by(TaxRate.id)
            ).all()
            for rate in rates:
                if _in_force(rate.effective_from, rate.effective_to, on_date):
                    results.append(
                        TaxAmount(
                            jurisdiction_id=jurisdiction.id,
                            name=rate.name,
                            rate=rate.rate,
                            taxable_base=base,
                            amount=round_money(base * rate.rate, currency),
                        )
                    )
        return results


default_engine: TaxEngine = TableTaxEngine()
