#!/usr/bin/env bash
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

# Nightly backup: the database (compressed SQL dump) and the file storage (logo, invoice PDFs),
# kept for KEEP_DAYS days. Run as root (systemd timer: deploy/systemd/).
#
#   sudo /opt/saumgm/deploy/backup.sh                         # the single instance
#   sudo /opt/saumgm-acme/deploy/backup.sh --instance acme    # one of several instances
#
# Single instance: database saumgm, files /var/lib/saumgm/storage, backups /var/backups/saumgm.
# Instance NAME:   database saumgm_NAME, files /var/lib/saumgm-NAME/storage,
#                  backups /var/backups/saumgm-NAME (docs/deploy/multiple-instances.md).
# DB_NAME, STORAGE_DIR, BACKUP_DIR and KEEP_DAYS in the environment override these.
#
# Database credentials come from /etc/saumgm/backup.cnf (/etc/saumgm/NAME-backup.cnf for an
# instance; [client] user=... password=...), or, if that file does not exist, root's unix-socket
# login on a local MariaDB.
# Copy the backups off the server too (restic, rsync, ...): see docs/deploy/ubuntu.md, step 9.
set -euo pipefail

INSTANCE=""
if [ "${1:-}" = "--instance" ]; then
  INSTANCE="${2:?--instance needs a name}"
  case "$INSTANCE" in
    *[!a-z0-9-]*) echo "Instance names use a-z, 0-9 and -" >&2; exit 2 ;;
  esac
fi

if [ -n "$INSTANCE" ]; then
  DB_NAME="${DB_NAME:-saumgm_${INSTANCE//-/_}}"
  STORAGE_DIR="${STORAGE_DIR:-/var/lib/saumgm-$INSTANCE/storage}"
  BACKUP_DIR="${BACKUP_DIR:-/var/backups/saumgm-$INSTANCE}"
  CNF=/etc/saumgm/$INSTANCE-backup.cnf
else
  DB_NAME="${DB_NAME:-saumgm}"
  STORAGE_DIR="${STORAGE_DIR:-/var/lib/saumgm/storage}"
  BACKUP_DIR="${BACKUP_DIR:-/var/backups/saumgm}"
  CNF=/etc/saumgm/backup.cnf
fi
KEEP_DAYS="${KEEP_DAYS:-30}"

stamp=$(date +%Y%m%d-%H%M%S)
umask 077
mkdir -p "$BACKUP_DIR"

client_opts=()
[ -f "$CNF" ] && client_opts=(--defaults-extra-file="$CNF")

db_file="$BACKUP_DIR/saumgm-db-$stamp.sql.gz"
mariadb-dump "${client_opts[@]}" --single-transaction --routines --events \
  --default-character-set=utf8mb4 --no-tablespaces "$DB_NAME" | gzip -9 > "$db_file.part"
mv "$db_file.part" "$db_file"

files_file="$BACKUP_DIR/saumgm-files-$stamp.tar.gz"
tar -C "$(dirname "$STORAGE_DIR")" -czf "$files_file.part" "$(basename "$STORAGE_DIR")"
mv "$files_file.part" "$files_file"

# A truncated dump ends without the completion marker; fail loudly instead of keeping it quietly.
if ! gzip -dc "$db_file" | tail -n 1 | grep -q "Dump completed"; then
  echo "Backup $db_file looks incomplete" >&2
  exit 1
fi

find "$BACKUP_DIR" -name 'saumgm-*.gz' -type f -mtime +"$KEEP_DAYS" -delete
echo "Backed up to $db_file and $files_file"
