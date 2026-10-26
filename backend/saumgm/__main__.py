# SauMGM - Sauen Management System: billing, sales tax and bookkeeping for small businesses
# Copyright (C) 2026 J. Thomas Stokkeland - https://www.saumgm.com/
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details. You should have received a copy of the
# GNU General Public License along with this program (the LICENSE file); if not, see
# <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Administration commands:

python -m saumgm create-organization --name "My Company"
python -m saumgm create-user --email me@example.com --name "Me" --role owner
python -m saumgm set-password --email me@example.com
python -m saumgm load-demo          # a demo business, into an empty database
"""

import argparse
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.config import get_settings
from saumgm.context import RequestContext, set_context
from saumgm.db import make_engine
from saumgm.demo import DEMO_PASSWORD, DEMO_USERS, DemoError, load_demo
from saumgm.enums import UserRoleType
from saumgm.models import Organization, User
from saumgm.seed import OrganizationSetup, create_organization
from saumgm.services import auth as auth_service


def read_password() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    return first


def cmd_create_organization(db: Session, args: argparse.Namespace) -> None:
    org = create_organization(
        db,
        OrganizationSetup(
            legal_name=args.legal_name or args.name,
            display_name=args.name,
            country_code=args.country,
            currency_code=args.currency,
            locale=args.locale,
            timezone=args.timezone,
        ),
    )
    db.commit()
    print(f"Created organization {org.id}: {org.display_name}")


def cmd_create_user(db: Session, args: argparse.Namespace) -> None:
    org_id = args.organization_id or db.scalars(select(Organization.id).order_by("id")).first()
    if org_id is None:
        raise SystemExit("No organization yet: run create-organization or the Access import first.")
    try:
        user = auth_service.create_user(
            db, org_id, args.email, args.name, UserRoleType(args.role), read_password()
        )
    except auth_service.PasswordPolicyError as exc:
        raise SystemExit(str(exc)) from None
    db.commit()
    print(f"Created user {user.id} ({user.email}) as {args.role} of organization {org_id}")


def cmd_set_password(db: Session, args: argparse.Namespace) -> None:
    user = db.scalars(
        select(User).where(User.email == auth_service.normalize_email(args.email))
    ).one_or_none()
    if user is None:
        raise SystemExit(f"No user {args.email}")
    try:
        auth_service.set_password(db, user, read_password())
    except auth_service.PasswordPolicyError as exc:
        raise SystemExit(str(exc)) from None
    auth_service.end_all_sessions(db, user.id)
    db.commit()
    print(f"Password changed for {user.email}; existing sessions signed out.")


def cmd_load_demo(db: Session, args: argparse.Namespace) -> None:
    set_context(db, RequestContext(batch_id="demo"))
    try:
        summary = load_demo(db)
    except DemoError as exc:
        raise SystemExit(str(exc)) from None
    db.commit()
    counts = ", ".join(f"{n} {what}" for what, n in summary.counts.items())
    print(f"Loaded the demo business {summary.organization.display_name!r}: {counts}.")
    print(f"Sign in as any of these, password {DEMO_PASSWORD!r}:")
    for email, _, role in DEMO_USERS:
        print(f"  {email}  ({role.value})")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m saumgm")
    sub = parser.add_subparsers(dest="command", required=True)

    org = sub.add_parser("create-organization", help="create a business (fresh installs)")
    org.add_argument("--name", required=True)
    org.add_argument("--legal-name")
    org.add_argument("--country", default="US")
    org.add_argument("--currency", default="USD")
    org.add_argument("--locale", default="en-US")
    org.add_argument("--timezone", default="America/New_York")
    org.set_defaults(func=cmd_create_organization)

    user = sub.add_parser("create-user", help="create a login (asks for the password)")
    user.add_argument("--email", required=True)
    user.add_argument("--name", required=True)
    user.add_argument("--role", choices=[r.value for r in UserRoleType], default="owner")
    user.add_argument("--organization-id", type=int)
    user.set_defaults(func=cmd_create_user)

    pw = sub.add_parser("set-password", help="reset a user's password")
    pw.add_argument("--email", required=True)
    pw.set_defaults(func=cmd_set_password)

    demo = sub.add_parser("load-demo", help="fill an empty database with a demo business")
    demo.set_defaults(func=cmd_load_demo)

    args = parser.parse_args(argv)
    engine = make_engine(get_settings().database_url)
    with Session(engine) as db:
        set_context(db, RequestContext())  # recorded as the system actor
        args.func(db, args)


if __name__ == "__main__":
    main()
