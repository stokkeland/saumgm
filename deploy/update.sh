#!/usr/bin/env bash
# Update a running installation to the latest code of the checked-out branch.
#
#   sudo /opt/saumgm/deploy/update.sh            # pull, install, migrate, build, restart
#   sudo /opt/saumgm/deploy/update.sh --no-pull  # use the code already in /opt/saumgm (e.g. rsynced)
#
# Takes a backup first. The frontend is built here if Node.js is installed; otherwise copy a
# frontend/dist built elsewhere before running this (see docs/deploy/ubuntu.md, step 6).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/saumgm}"
PULL=1
[ "${1:-}" = "--no-pull" ] && PULL=0

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi
cd "$APP_DIR"

echo "== Backup"
"$APP_DIR/deploy/backup.sh"

if [ "$PULL" -eq 1 ]; then
  echo "== Pull"
  git pull --ff-only
fi

echo "== Backend"
backend/.venv/bin/pip install --quiet --upgrade pip
backend/.venv/bin/pip install --quiet -e backend
(cd backend && sudo -u saumgm .venv/bin/alembic upgrade head)

if command -v npm >/dev/null; then
  echo "== Frontend"
  (cd frontend && npm ci --no-audit --no-fund && npm run build)
else
  echo "== Frontend: Node.js not installed; using the frontend/dist that is already here"
fi
[ -f frontend/dist/index.html ] || { echo "frontend/dist/index.html is missing" >&2; exit 1; }

echo "== Restart"
systemctl restart saumgm
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "API is up: $(curl -fsS http://127.0.0.1:8000/api/health)"
    exit 0
  fi
  sleep 1
done
echo "API did not answer on :8000; see: journalctl -u saumgm -n 50" >&2
exit 1
