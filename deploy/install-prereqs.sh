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

# Check, and optionally install, what SauMGM needs on Ubuntu 24.04.
#
#   sudo deploy/install-prereqs.sh --check          # only report; changes nothing
#   sudo deploy/install-prereqs.sh                  # install what is missing
#   sudo deploy/install-prereqs.sh --with-node      # also Node.js 24 (to build the frontend here)
#   sudo deploy/install-prereqs.sh --with-mariadb   # also MariaDB server (if the DB is on this host)
#   sudo deploy/install-prereqs.sh --instance acme  # user and folders for instance "acme"
#                                                   # (docs/deploy/multiple-instances.md)
#
# It never removes or upgrades packages that are already installed, and never touches databases.
# See docs/deploy/ubuntu.md for the whole procedure.
set -euo pipefail

CHECK_ONLY=0
WITH_NODE=0
WITH_MARIADB=0
INSTANCE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --with-node) WITH_NODE=1 ;;
    --with-mariadb) WITH_MARIADB=1 ;;
    --instance) INSTANCE="${2:?--instance needs a name}"; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$INSTANCE" in
  *[!a-z0-9-]*) echo "Instance names use a-z, 0-9 and -" >&2; exit 2 ;;
esac
# The single instance runs as "saumgm"; instance NAME as "saumgm-NAME" with its own folders.
SUFFIX="${INSTANCE:+-$INSTANCE}"
SERVICE_USER="saumgm$SUFFIX"

MIN_PYTHON="3.12"
MIN_MARIADB="10.11"
NODE_MAJOR=24
MIN_NODE="20.19"   # Vite 8 needs Node 20.19+ or 22.12+

# Packages: Python runtime and venv, Apache, MariaDB client (backups, imports), TLS, tools.
# Python wheels exist for every dependency (argon2, ReportLab, Pillow), so no compilers are needed.
PACKAGES=(
  python3 python3-venv python3-pip
  apache2 mariadb-client
  certbot python3-certbot-apache
  git rsync curl ca-certificates gzip tzdata
)
APACHE_MODULES=(proxy proxy_http headers rewrite ssl expires)

ok()   { printf '  \033[32mok\033[0m       %s\n' "$*"; }
miss() { printf '  \033[33mmissing\033[0m  %s\n' "$*"; }
bad()  { printf '  \033[31mproblem\033[0m  %s\n' "$*"; }
# version_ge A B: true if version A >= B
version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]; }

if [ "$CHECK_ONLY" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo to install (or use --check)." >&2
  exit 1
fi

echo "System"
# shellcheck source=/dev/null
. /etc/os-release
if [ "${ID:-}" = "ubuntu" ] && [ "${VERSION_ID:-}" = "24.04" ]; then
  ok "Ubuntu $VERSION_ID"
else
  bad "${PRETTY_NAME:-unknown OS}: written for Ubuntu 24.04; package names may differ"
fi

echo "Packages"
missing=()
for pkg in "${PACKAGES[@]}"; do
  if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
    ok "$pkg"
  else
    miss "$pkg"
    missing+=("$pkg")
  fi
done
if [ "$WITH_MARIADB" -eq 1 ]; then
  if dpkg-query -W -f='${Status}' mariadb-server 2>/dev/null | grep -q "install ok installed"; then
    ok "mariadb-server"
  else
    miss "mariadb-server"
    missing+=(mariadb-server)
  fi
fi

if [ "${#missing[@]}" -gt 0 ] && [ "$CHECK_ONLY" -eq 0 ]; then
  echo "Installing: ${missing[*]}"
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${missing[@]}"
fi

echo "Versions"
if command -v python3 >/dev/null; then
  pv=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  if version_ge "$pv" "$MIN_PYTHON"; then ok "Python $pv"; else bad "Python $pv (need $MIN_PYTHON+)"; fi
  if python3 -c 'import venv, ensurepip' 2>/dev/null; then ok "python3 venv"; else miss "python3-venv"; fi
else
  miss "python3"
fi

if command -v mariadb >/dev/null; then
  ok "MariaDB client $(mariadb --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)"
fi
if command -v mariadbd >/dev/null || [ -x /usr/sbin/mariadbd ]; then
  sv=$( (mariadbd --version 2>/dev/null || /usr/sbin/mariadbd --version) | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)
  if version_ge "$sv" "$MIN_MARIADB"; then ok "MariaDB server $sv (local)"; else bad "MariaDB server $sv (need $MIN_MARIADB+)"; fi
  if systemctl is-active --quiet mariadb; then ok "mariadb service running"; else bad "mariadb service not running"; fi
else
  echo "  info     no MariaDB server on this host (fine if the database is elsewhere; --with-mariadb installs one)"
fi

if command -v node >/dev/null; then
  nv=$(node --version | tr -d v)
  if version_ge "$nv" "$MIN_NODE"; then
    ok "Node.js $nv"
  else
    bad "Node.js $nv is too old to build the frontend (need $MIN_NODE+; --with-node installs $NODE_MAJOR)"
    if [ "$WITH_NODE" -eq 1 ]; then NEED_NODE=1; fi
  fi
else
  if [ "$WITH_NODE" -eq 1 ]; then
    miss "Node.js"
    NEED_NODE=1
  else
    echo "  info     no Node.js (only needed to build the frontend on this server; --with-node installs it)"
  fi
fi
if [ "${NEED_NODE:-0}" -eq 1 ] && [ "$CHECK_ONLY" -eq 0 ]; then
  echo "Installing Node.js $NODE_MAJOR from NodeSource"
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource_setup.sh
  bash /tmp/nodesource_setup.sh
  apt-get install -y -q nodejs
  ok "Node.js $(node --version)"
fi

echo "Apache modules"
if command -v a2query >/dev/null; then
  for mod in "${APACHE_MODULES[@]}"; do
    if a2query -m "$mod" >/dev/null 2>&1; then
      ok "$mod"
    elif [ "$CHECK_ONLY" -eq 0 ]; then
      a2enmod -q "$mod" && ok "$mod (enabled now)"
      RELOAD_APACHE=1
    else
      miss "$mod"
    fi
  done
  if [ "${RELOAD_APACHE:-0}" -eq 1 ]; then
    systemctl restart apache2
    echo "  Apache restarted to load the new modules"
  fi
else
  miss "apache2 (a2query not found)"
fi

echo "Service account and folders"
if id "$SERVICE_USER" >/dev/null 2>&1; then
  ok "user $SERVICE_USER"
elif [ "$CHECK_ONLY" -eq 0 ]; then
  useradd --system --home-dir "/var/lib/saumgm$SUFFIX" --shell /usr/sbin/nologin "$SERVICE_USER"
  ok "user $SERVICE_USER (created)"
else
  miss "user $SERVICE_USER"
fi
for dir in "/var/lib/saumgm$SUFFIX/storage" "/var/backups/saumgm$SUFFIX"; do
  if [ -d "$dir" ]; then
    ok "$dir"
  elif [ "$CHECK_ONLY" -eq 0 ]; then
    install -d -m 750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$dir"
    ok "$dir (created)"
  else
    miss "$dir"
  fi
done

echo
if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "Check finished; nothing was changed. Run without --check (with sudo) to install what is missing."
else
  echo "Done. Next: docs/deploy/ubuntu.md, step 2 (database)."
fi
