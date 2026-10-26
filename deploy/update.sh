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

# Update a running installation to the latest code of the checked-out branch.
#
#   sudo /opt/saumgm/deploy/update.sh                          # pull, install, migrate, build, restart
#   sudo /opt/saumgm/deploy/update.sh --no-pull                # use the code already there
#   sudo /opt/saumgm-acme/deploy/update.sh --instance acme     # one of several instances
#
# Takes a backup first. The frontend is built here if Node.js is installed; otherwise copy a
# frontend/dist built elsewhere before running this (see docs/deploy/ubuntu.md, step 6).
# Instances: /opt/saumgm-NAME, service saumgm@NAME, port from /etc/saumgm/NAME.env
# (docs/deploy/multiple-instances.md).
set -euo pipefail

PULL=1
INSTANCE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull) PULL=0 ;;
    --instance) INSTANCE="${2:?--instance needs a name}"; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ -n "$INSTANCE" ]; then
  case "$INSTANCE" in
    *[!a-z0-9-]*) echo "Instance names use a-z, 0-9 and -" >&2; exit 2 ;;
  esac
  APP_DIR="${APP_DIR:-/opt/saumgm-$INSTANCE}"
  SERVICE="saumgm@$INSTANCE"
  SERVICE_USER="saumgm-$INSTANCE"
  PORT=$(sed -n 's/^PORT=//p' "/etc/saumgm/$INSTANCE.env" | tail -n 1)
  [ -n "$PORT" ] || { echo "No PORT= in /etc/saumgm/$INSTANCE.env" >&2; exit 1; }
  BACKUP_ARGS=(--instance "$INSTANCE")
else
  APP_DIR="${APP_DIR:-/opt/saumgm}"
  SERVICE=saumgm
  SERVICE_USER=saumgm
  PORT=8000
  BACKUP_ARGS=()
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi
cd "$APP_DIR"

echo "== Backup"
"$APP_DIR/deploy/backup.sh" "${BACKUP_ARGS[@]}"

if [ "$PULL" -eq 1 ]; then
  echo "== Pull"
  git pull --ff-only
fi

echo "== Backend"
backend/.venv/bin/pip install --quiet --upgrade pip
backend/.venv/bin/pip install --quiet -e backend
(cd backend && sudo -u "$SERVICE_USER" .venv/bin/alembic upgrade head)

if command -v npm >/dev/null; then
  echo "== Frontend"
  (cd frontend && npm ci --no-audit --no-fund && npm run build)
else
  echo "== Frontend: Node.js not installed; using the frontend/dist that is already here"
fi
[ -f frontend/dist/index.html ] || { echo "frontend/dist/index.html is missing" >&2; exit 1; }

echo "== Restart $SERVICE"
systemctl restart "$SERVICE"
for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    echo "API is up: $(curl -fsS "http://127.0.0.1:$PORT/api/health")"
    exit 0
  fi
  sleep 1
done
echo "API did not answer on :$PORT; see: journalctl -u $SERVICE -n 50" >&2
exit 1
