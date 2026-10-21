"""Business numbers (invoice no., contact no.) from counter rows, never from AUTO_INCREMENT ids.

The counter row is locked (SELECT ... FOR UPDATE) for the rest of the transaction, so two
concurrent requests cannot get the same number. On a Galera cluster a conflicting commit fails
certification instead and the request is retried by the client.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.models import NumberSequence

DEFAULTS = {
    "invoice": ("", 0, 1),
    "credit_note": ("CN-", 0, 1),
    "party": ("", 8, 1),
}


def next_number(session: Session, organization_id: int, name: str) -> str:
    seq = session.scalars(
        select(NumberSequence)
        .where(NumberSequence.organization_id == organization_id, NumberSequence.name == name)
        .with_for_update()
    ).one_or_none()
    if seq is None:
        prefix, pad, start = DEFAULTS[name]
        seq = NumberSequence(
            organization_id=organization_id,
            name=name,
            next_value=start,
            prefix=prefix,
            pad_width=pad,
        )
        session.add(seq)
        session.flush()
    number = seq.format(seq.next_value)
    seq.next_value += 1
    return number
