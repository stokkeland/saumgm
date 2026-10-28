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
#   sudo /opt/saumgm/deploy/update.sh --branch release/v2.0    # move to another branch first
#   sudo /opt/saumgm/deploy/update.sh --no-pull                # use the code already there
#   sudo /opt/saumgm-acme/deploy/update.sh --instance acme     # one of several instances
#
# Read docs/upgrading.md before moving to a new version. Takes a backup first. The frontend is
# built here if Node.js is installed; otherwise copy a frontend/dist built elsewhere before
# running this (see docs/deploy/ubuntu.md, step 6).
# Instances: /opt/saumgm-NAME, service saumgm@NAME, port from /etc/saumgm/NAME.env
# (docs/deploy/multiple-instances.md).
set -euo pipefail

PULL=1
BACKUP=1
INSTANCE=""
BRANCH=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull) PULL=0 ;;
    --skip-backup) BACKUP=0 ;;  # used when the script restarts itself after pulling
    --branch) BRANCH="${2:?--branch needs a name}"; shift ;;
    --instance) INSTANCE="${2:?--instance needs a name}"; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
if [ -n "$BRANCH" ] && [ "$PULL" -eq 0 ]; then
  echo "--branch fetches from git, so it cannot be combined with --no-pull" >&2
  exit 2
fi

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

if [ "$PULL" -eq 1 ] && [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Files in $APP_DIR were changed by hand (git status); commit, stash or undo them first" >&2
  exit 1
fi

if [ "$BACKUP" -eq 1 ]; then
  echo "== Backup"
  "$APP_DIR/deploy/backup.sh" "${BACKUP_ARGS[@]}"
fi

if [ "$PULL" -eq 1 ]; then
  if [ -n "$BRANCH" ] && [ "$BRANCH" != "$(git rev-parse --abbrev-ref HEAD)" ]; then
    echo "== Switch to $BRANCH"
    git fetch origin
    git switch "$BRANCH"
  fi
  echo "== Pull ($(git rev-parse --abbrev-ref HEAD))"
  git pull --ff-only
  # The pull may have replaced this script while bash is reading it. Continue with the new copy,
  # so the remaining steps are those of the version just pulled. (This block is parsed whole
  # before it runs, so the exec is safe.)
  INSTANCE_ARGS=()
  [ -n "$INSTANCE" ] && INSTANCE_ARGS=(--instance "$INSTANCE")
  exec bash "$APP_DIR/deploy/update.sh" --no-pull --skip-backup "${INSTANCE_ARGS[@]}"
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
    HEALTH=$(curl -fsS "http://127.0.0.1:$PORT/api/health")
    echo "API is up: $HEALTH"
    case "$HEALTH" in
      *'"schema_current":false'*)
        echo "The database schema is not the newest one; see: alembic current / alembic heads" >&2
        exit 1 ;;
    esac
    exit 0
  fi
  sleep 1
done
echo "API did not answer on :$PORT; see: journalctl -u $SERVICE -n 50" >&2
exit 1
