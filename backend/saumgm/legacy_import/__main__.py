"""Command line:  python -m saumgm.legacy_import --mdb PATH --config PATH [--reset] [--report PATH]

Reads the Access database, archives it verbatim into legacy_* tables, maps it into the SauMGM
schema in one transaction, reconciles, and writes a Markdown report. Exit code 1 if the
reconciliation fails (the import is rolled back unless --keep-on-mismatch is given).
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from saumgm.config import get_settings
from saumgm.db import make_engine
from saumgm.legacy_import.archive import write_archive
from saumgm.legacy_import.config import load_config
from saumgm.legacy_import.mapping import import_access
from saumgm.legacy_import.reconcile import reconcile
from saumgm.legacy_import.report import render_report
from saumgm.legacy_import.source import read_access
from saumgm.models import Base, Organization


def clear_application_tables(conn: Connection) -> None:
    """Delete all rows from the application tables (not the archive, not alembic_version)."""
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    try:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    finally:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m saumgm.legacy_import", description=__doc__)
    parser.add_argument("--mdb", type=Path, required=True, help="the Access .mdb file")
    parser.add_argument("--config", type=Path, required=True, help="import config (TOML)")
    parser.add_argument("--report", type=Path, help="where to write the report (Markdown)")
    parser.add_argument(
        "--reset", action="store_true", help="delete all existing application data first"
    )
    parser.add_argument(
        "--keep-on-mismatch",
        action="store_true",
        help="commit the import even if the reconciliation finds differences",
    )
    args = parser.parse_args(argv)
    report_path: Path = args.report or args.mdb.with_name("import_report.md")

    config = load_config(args.config)
    print(f"Reading {args.mdb} ...")
    data = read_access(args.mdb)
    print(f"  {len(data)} tables, {sum(len(t.rows) for t in data.values())} rows")

    engine = make_engine(get_settings().database_url)
    with engine.begin() as conn:
        if "organization" not in inspect(conn).get_table_names():
            print("The database has no schema yet; run `alembic upgrade head` first.")
            return 2
        archive_counts = write_archive(conn, data)
    print(f"Archived {len(archive_counts)} tables into legacy_*")

    # Clearing, importing and reconciling happen in one transaction: all or nothing.
    with Session(engine) as session:
        if session.query(Organization).count():
            if not args.reset:
                print("The database already holds data; use --reset to replace it.")
                return 2
            clear_application_tables(session.connection())
            print("Cleared existing application data")

        result = import_access(session, data, config)
        session.expire_all()
        checks = reconcile(session, data, result)
        failed = [c for c in checks if not c.ok]

        report_path.write_text(
            render_report(result, checks, archive_counts, str(args.mdb)), encoding="utf-8"
        )
        print(f"Report: {report_path}")
        print(f"Reconciliation: {len(checks) - len(failed)}/{len(checks)} checks match")
        print(f"Data issues to review: {len(result.issues)}")
        if failed and not args.keep_on_mismatch:
            session.rollback()
            print("Import rolled back because of mismatches (see report).")
            return 1
        session.commit()
    print("Import committed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
