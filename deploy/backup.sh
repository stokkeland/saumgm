#!/usr/bin/env bash
# Nightly backup: the database (compressed SQL dump) and the file storage (logo, invoice PDFs),
# kept for KEEP_DAYS days in /var/backups/saumgm. Run as root (systemd timer: deploy/systemd/).
#
#   sudo /opt/saumgm/deploy/backup.sh
#
# Database credentials come from /etc/saumgm/backup.cnf ([client] user=... password=...), or, if
# that file does not exist, root's unix-socket login on a local MariaDB.
# Copy the backups off the server too (restic, rsync, ...): see docs/deploy/ubuntu.md, step 9.
set -euo pipefail

DB_NAME="${DB_NAME:-saumgm}"
STORAGE_DIR="${STORAGE_DIR:-/var/lib/saumgm/storage}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/saumgm}"
KEEP_DAYS="${KEEP_DAYS:-30}"
CNF=/etc/saumgm/backup.cnf

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
