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

"""Export the database named in backend/.env to an SQL file that loads into MariaDB 10.11+.

Run with the backend's Python (on the development machine):

    backend/.venv/Scripts/python deploy/export_database.py tmp/saumgm.sql      (Windows)
    backend/.venv/bin/python deploy/export_database.py tmp/saumgm.sql          (Linux)

Differences from a plain mariadb-dump:
- login sessions (auth_session rows) are left out; everyone signs in again on the new server;
- MariaDB 11+ default collations (uca1400), which 10.x does not have, become the 10.x ones;
- the "sandbox mode" first line written by newer mariadb-dump, which older clients reject, is
  dropped;
- no CREATE DATABASE, so it loads into whatever (empty) database you choose.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy.engine import make_url  # noqa: E402

from saumgm.config import get_settings  # noqa: E402

COLLATIONS = {
    "utf8mb3_uca1400_ai_ci": "utf8mb3_general_ci",
    "utf8mb4_uca1400_ai_ci": "utf8mb4_unicode_ci",
}


def find_dump() -> str:
    for name in ("mariadb-dump", "mysqldump"):
        if found := shutil.which(name):
            return found
    for candidate in sorted(Path("C:/Program Files").glob("MariaDB */bin/mariadb-dump.exe")):
        return str(candidate)
    raise SystemExit("mariadb-dump not found; put MariaDB's bin folder on PATH")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    url = make_url(get_settings().database_url)
    command = [
        find_dump(),
        f"--host={url.host or '127.0.0.1'}",
        f"--port={url.port or 3306}",
        f"--user={url.username}",
        "--single-transaction",
        "--default-character-set=utf8mb4",
        "--no-tablespaces",
        "--skip-dump-date",
        "--hex-blob",
        "--routines",
        "--events",
        f"--ignore-table-data={url.database}.auth_session",
        str(url.database),
    ]
    env = dict(os.environ, MYSQL_PWD=url.password or "")
    result = subprocess.run(command, env=env, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(result.stderr.decode(errors="replace"))

    lines = result.stdout.decode("utf-8").splitlines()
    if lines and lines[0].startswith("/*M!999999"):
        lines = lines[1:]
    sql = "\n".join(lines) + "\n"
    for unsupported, replacement in COLLATIONS.items():
        sql = sql.replace(unsupported, replacement)
    if not sql.rstrip().endswith("Dump completed"):
        raise SystemExit("The dump looks incomplete")

    header = (
        f"-- SauMGM export of database {url.database} (loads into MariaDB 10.11+).\n"
        "-- Load into an EMPTY utf8mb4 database; see docs/deploy/ubuntu.md, step 5.\n"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header + sql, encoding="utf-8", newline="\n")
    tables = len(re.findall(r"^CREATE TABLE", sql, flags=re.MULTILINE))
    print(f"Wrote {args.output} ({args.output.stat().st_size // 1024} KiB, {tables} tables)")


if __name__ == "__main__":
    main()
