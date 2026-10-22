# Installing SauMGM on Ubuntu 24.04 with Apache and MariaDB

This guide takes a fresh Ubuntu 24.04 server to a running SauMGM at `https://saumgm.example.com`
(use your own host name throughout). Expect about an hour. Every file mentioned under `deploy/` is
in this repository.

```
Browser ──HTTPS──> Apache :443 ─┬─ /            → /opt/saumgm/frontend/dist  (built React app)
                                └─ /api/...     → uvicorn 127.0.0.1:8000     (systemd: saumgm)
                                                     ├─> MariaDB  (database saumgm)
                                                     └─> /var/lib/saumgm/storage  (logo, invoice PDFs)
```

| Path | What | Owner |
|---|---|---|
| `/opt/saumgm` | the code (git checkout), with `backend/.venv` and `frontend/dist` | root |
| `/opt/saumgm/backend/.env` | configuration and the database password | root:saumgm, mode 640 |
| `/var/lib/saumgm/storage` | stored files | saumgm |
| `/var/backups/saumgm` | nightly backups | root (saumgm group) |

The API runs as the unprivileged system user `saumgm`, which can only write to
`/var/lib/saumgm`.

Contents:

1. [Packages](#1-packages)
2. [Database](#2-database)
3. [Code and Python environment](#3-code-and-python-environment)
4. [Configuration](#4-configuration)
5. [Load your data](#5-load-your-data)
6. [Frontend](#6-frontend)
7. [API service](#7-api-service)
8. [Apache and HTTPS](#8-apache-and-https)
9. [Backups](#9-backups)
10. [Updating](#10-updating)
11. [Switching over from Access](#11-switching-over-from-access)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Packages

| Package | Why |
|---|---|
| `python3` (3.12 on 24.04), `python3-venv`, `python3-pip` | runs the API; the app's own libraries go into a virtual environment, not the system |
| `apache2` | web server: serves the app, proxies the API, terminates HTTPS |
| `mariadb-client` | `mariadb` and `mariadb-dump` for loading data and backups |
| `mariadb-server` (10.11 on 24.04) | only if the database runs on this server and is not installed yet |
| `certbot`, `python3-certbot-apache` | free Let's Encrypt certificates, renewed automatically |
| `git`, `rsync`, `curl`, `ca-certificates`, `gzip`, `tzdata` | fetching code, copying files, health checks, backups |
| Node.js 20.19+ (24 recommended) | **optional**: only to build the frontend on the server; Ubuntu's own `nodejs` (18) is too old, so the script uses NodeSource |
| Apache modules `proxy proxy_http headers rewrite ssl expires` | reverse proxy, headers, HTTPS |

No compilers or `-dev` packages are needed: every Python dependency (argon2, ReportLab, Pillow,
PyMySQL) installs from ready-made wheels.

The script `deploy/install-prereqs.sh` checks all of this, installs what is missing, enables the
Apache modules, and creates the `saumgm` user and its folders. It never upgrades or removes
anything that is already there.

Get the repository onto the server first (step 3 explains the options), or copy just the script.

```sh
sudo bash deploy/install-prereqs.sh --check        # report only
sudo bash deploy/install-prereqs.sh                # install what is missing
sudo bash deploy/install-prereqs.sh --with-node    # ... and Node.js 24, to build the frontend here
sudo bash deploy/install-prereqs.sh --with-mariadb # ... and MariaDB server, if the DB lives here
```

The same packages by hand:

```sh
sudo apt update
sudo apt install python3 python3-venv python3-pip apache2 mariadb-client \
    certbot python3-certbot-apache git rsync curl ca-certificates gzip tzdata
sudo a2enmod proxy proxy_http headers rewrite ssl expires && sudo systemctl restart apache2
sudo useradd --system --home-dir /var/lib/saumgm --shell /usr/sbin/nologin saumgm
sudo install -d -m 750 -o saumgm -g saumgm /var/lib/saumgm/storage /var/backups/saumgm
```

## 2. Database

SauMGM needs MariaDB **10.11 or newer** (CI tests 10.11). Check the server version:

```sh
sudo mariadb -e "SELECT VERSION();"
```

Create the database and an application user. Pick a long random password, for example from
`openssl rand -base64 24`:

```sh
sudo mariadb <<'SQL'
CREATE DATABASE saumgm CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'saumgm'@'localhost' IDENTIFIED BY 'CHANGE-ME';
GRANT ALL PRIVILEGES ON saumgm.* TO 'saumgm'@'localhost';
SQL
```

- **Database on another host:** create the user as `'saumgm'@'<app server IP>'` and use that
  host in `DATABASE_URL`. Keep port 3306 closed to everything except the app server.
- **Galera later:** every table is InnoDB with a primary key and the app uses no
  cluster-unsafe features, so the same schema runs on a Galera cluster unchanged.

## 3. Code and Python environment

Put the repository in `/opt/saumgm`. Choose one:

- **git (recommended; updates become `git pull`).** The GitHub repository is private, so give the
  server read access with a deploy key:
  ```sh
  sudo ssh-keygen -t ed25519 -f /root/.ssh/saumgm_deploy -N ""
  sudo cat /root/.ssh/saumgm_deploy.pub    # GitHub → repo → Settings → Deploy keys → Add (read-only)
  printf 'Host github.com\n  IdentityFile /root/.ssh/saumgm_deploy\n' | sudo tee -a /root/.ssh/config
  sudo git clone --branch main git@github.com:stokkeland/sau_mgm.git /opt/saumgm
  ```
  Deploy from `main`. The work so far is on the branch `dev/initial`; merge it into `main` first
  (a pull request on GitHub), or clone with `--branch dev/initial` until then.
- **Copy from your PC** (Git Bash). Copy without `.venv`, `node_modules`, `.env` or `tmp`:
  ```sh
  rsync -av --exclude .git --exclude .venv --exclude node_modules --exclude tmp \
      --exclude storage --exclude '.env' ./ admin@server:/tmp/saumgm/
  # then on the server:  sudo mv /tmp/saumgm /opt/saumgm && sudo chown -R root:root /opt/saumgm
  ```

Create the Python environment and install the backend:

```sh
cd /opt/saumgm
sudo python3 -m venv backend/.venv
sudo backend/.venv/bin/pip install --upgrade pip
sudo backend/.venv/bin/pip install -e backend
sudo backend/.venv/bin/python -c "import saumgm, reportlab, argon2; print('ok')"
```

(The `legacy` extra, which provides the Access importer, is not needed on the server. Imports
run on Windows; the server gets the resulting SQL file, as described in step 5.)

## 4. Configuration

All settings live in `/opt/saumgm/backend/.env`. Business settings such as company name, currency
and tax are not in this file; they are kept in the database and edited in the app.

```sh
sudo tee /opt/saumgm/backend/.env >/dev/null <<'EOF'
DATABASE_URL=mysql+pymysql://saumgm:CHANGE-ME@127.0.0.1:3306/saumgm?charset=utf8mb4
STORAGE_URL=file:///var/lib/saumgm/storage
ENVIRONMENT=production
LOG_LEVEL=INFO
# Same-origin setup (Apache serves both the app and /api): no CORS needed.
CORS_ORIGINS=
EOF
sudo chown root:saumgm /opt/saumgm/backend/.env
sudo chmod 640 /opt/saumgm/backend/.env
```

| Setting | Meaning |
|---|---|
| `DATABASE_URL` | MariaDB connection. If the password contains `@ : / ?` or `#`, URL-encode it (`python3 -c "import urllib.parse; print(urllib.parse.quote('p@ss', safe=''))"`) |
| `STORAGE_URL` | where files are stored; `file://` + an absolute path |
| `ENVIRONMENT=production` | among other things, session cookies are sent only over HTTPS |
| `COOKIE_SECURE` | override for the above; set `false` **only** to test over plain HTTP before TLS works, then remove |
| `SESSION_DAYS` | how long a login lasts (default 14) |
| `LOG_LEVEL` | `INFO` normally; `DEBUG` when chasing a problem |

## 5. Load your data

### Option A: your existing data (from the development PC)

On the PC, export the database the development app uses. `tmp/saumgm.sql` already contains one
export; make a fresh one right before going live so it includes your latest changes:

```sh
backend/.venv/Scripts/python deploy/export_database.py tmp/saumgm.sql
scp tmp/saumgm.sql admin@server:/tmp/
```

The export is adjusted for MariaDB 10.11:
- MariaDB 11+ collations are mapped to 10.x ones.
- Login sessions are left out.
- It has no `CREATE DATABASE`, so it loads into the database from step 2.

On the server:

```sh
sudo mariadb --default-character-set=utf8mb4 saumgm < /tmp/saumgm.sql
cd /opt/saumgm/backend && sudo -u saumgm .venv/bin/alembic upgrade head   # newer schema changes, if any
sudo mariadb saumgm -e "SELECT COUNT(*) AS invoices FROM invoice; SELECT email FROM app_user;"
shred -u /tmp/saumgm.sql     # it contains password hashes and all business data
```

User accounts and passwords come along, so sign in exactly as on the PC.

If the development database has stored files (an uploaded logo, PDFs of invoices issued there),
copy the PC's `storage/` folder into `/var/lib/saumgm/storage/` as well and run
`sudo chown -R saumgm:saumgm /var/lib/saumgm/storage`. Otherwise just upload the logo again in
Settings → Business.

### Option B: a new, empty business

```sh
cd /opt/saumgm/backend
sudo -u saumgm .venv/bin/alembic upgrade head
sudo -u saumgm .venv/bin/python -m saumgm create-organization --name "My Company"
sudo -u saumgm .venv/bin/python -m saumgm create-user --email you@example.com --name "Your Name" --role owner
```

## 6. Frontend

The frontend is static files in `frontend/dist`. Build it on either machine; the result is the
same.

- **On the server** (Node.js from `install-prereqs.sh --with-node`):
  ```sh
  cd /opt/saumgm/frontend && sudo npm ci --no-audit --no-fund && sudo npm run build
  ```
- **On the PC**, then copy:
  ```sh
  cd frontend && npm ci && npm run build
  rsync -av --delete dist/ admin@server:/tmp/saumgm-dist/
  # on the server:
  sudo rsync -a --delete /tmp/saumgm-dist/ /opt/saumgm/frontend/dist/
  ```

## 7. API service

```sh
sudo cp /opt/saumgm/deploy/systemd/saumgm.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now saumgm
systemctl status saumgm --no-pager
curl -s http://127.0.0.1:8000/api/health        # {"status":"ok","database":"ok",...}
```

The unit runs two uvicorn workers on `127.0.0.1:8000` as user `saumgm`, restarts the API if it
crashes, and takes the client's real IP from Apache for the audit log. For more traffic, raise
`--workers` (about one per CPU core).

## 8. Apache and HTTPS

1. Point DNS for the host name at the server, and open the firewall:
   `sudo ufw allow 'Apache Full'` (if `ufw` is on).
2. Install the site. Edit `ServerName` first:
   ```sh
   sudo cp /opt/saumgm/deploy/apache/saumgm.conf /etc/apache2/sites-available/
   sudo nano /etc/apache2/sites-available/saumgm.conf          # ServerName saumgm.example.com
   sudo a2ensite saumgm
   sudo a2dissite 000-default        # only if nothing else uses the default site
   sudo apache2ctl configtest && sudo systemctl reload apache2
   ```
3. Get a certificate. Certbot creates the HTTPS site and the HTTP→HTTPS redirect, and renews it
   automatically:
   ```sh
   sudo certbot --apache -d saumgm.example.com
   sudo certbot renew --dry-run
   ```
4. Once HTTPS works, uncomment the `Strict-Transport-Security` line in
   `/etc/apache2/sites-available/saumgm-le-ssl.conf` and reload Apache.
5. Open `https://saumgm.example.com` and sign in. Check that an invoice PDF opens, and that a
   report downloads as CSV.

If the server already hosts other sites, this vhost only adds a new name and does not affect them.
To put SauMGM under a path of an existing site instead (e.g. `/saumgm/`), the frontend has to be
built with a different base path. That is not set up yet; a separate host name is simpler.

## 9. Backups

`deploy/backup.sh` writes a compressed database dump and an archive of the stored files to
`/var/backups/saumgm` and keeps them for 30 days. Install it as a nightly timer:

```sh
sudo chmod +x /opt/saumgm/deploy/*.sh
sudo cp /opt/saumgm/deploy/systemd/saumgm-backup.service /opt/saumgm/deploy/systemd/saumgm-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now saumgm-backup.timer
sudo systemctl start saumgm-backup.service && ls -lh /var/backups/saumgm     # run one now
```

- **Database credentials.** With MariaDB on the same server, the script logs in as root over the
  local socket, so no password is needed. For a remote database, put credentials in
  `/etc/saumgm/backup.cnf` (mode 600):
  ```ini
  [client]
  host=db.example.lan
  user=saumgm
  password=CHANGE-ME
  ```
- **Off-site copies.** Backups on the same disk do not survive losing the server. Copy them
  elsewhere, for example with restic to Backblaze B2, S3 or another server:
  ```sh
  sudo apt install restic
  # once: restic -r sftp:backup@otherhost:/srv/restic/saumgm init
  # nightly, e.g. as ExecStartPost in saumgm-backup.service:
  restic -r sftp:backup@otherhost:/srv/restic/saumgm backup /var/backups/saumgm --password-file /etc/saumgm/restic.pass
  ```
- **Restore (test this once).** Into a scratch database, to see that a backup is good:
  ```sh
  sudo mariadb -e "CREATE DATABASE saumgm_restore_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
  gunzip -c /var/backups/saumgm/saumgm-db-YYYYMMDD-HHMMSS.sql.gz | sudo mariadb saumgm_restore_test
  sudo mariadb saumgm_restore_test -e "SELECT COUNT(*) FROM invoice"
  sudo mariadb -e "DROP DATABASE saumgm_restore_test"
  ```
  A real restore follows the same steps into `saumgm`, after stopping the API and recreating the
  database. Then unpack the files archive into `/var/lib/` and start the API again:
  ```sh
  sudo systemctl stop saumgm
  sudo tar -C /var/lib -xzf /var/backups/saumgm/saumgm-files-YYYYMMDD-HHMMSS.tar.gz
  sudo systemctl start saumgm
  ```

## 10. Updating

```sh
sudo /opt/saumgm/deploy/update.sh
```

The script:
1. Backs up the database and files.
2. Runs `git pull`.
3. Updates the Python packages.
4. Applies database migrations.
5. Builds the frontend, if Node.js is installed.
6. Restarts the API and waits for the health check.

If you copy code instead of using git, run it with `--no-pull` (and copy a fresh `frontend/dist`
if the server has no Node.js).

Database migrations only ever move forward. Read the release notes (the git log) before
updating, and keep the backup that the script just made until the new version has run for a day.

## 11. Switching over from Access

1. Stop entering data in Access.
2. Bring the development data up to date. Either keep the development database as it is (if
   it already holds everything), or re-import the final `.mdb` on the PC; see the main
   README, "Importing the old MS Access database".
3. Export and load it (step 5, option A), then check on the server:
   - Dashboard: receivables and overdue match what you expect.
   - Reports → Receivables aging: the totals per client look right.
   - Open a few recent invoices and their PDFs.
4. Upload the logo (Settings → Business) and check the business details, addresses and sales-tax
   registration (Settings).
5. Create accounts for anyone else who needs access (Settings → Users).
6. Keep the `.mdb` and the import report: the import keeps the raw old records too, but the
   original file is your reference.

## 12. Troubleshooting

| Symptom | Look at |
|---|---|
| Site shows "Service Unavailable" / 502 | API not running: `systemctl status saumgm`, `journalctl -u saumgm -n 100` |
| API fails at start with a database error | `DATABASE_URL` in `.env` (password encoding, host, user grants); `mariadb -u saumgm -p saumgm` works? |
| Sign-in succeeds but you are immediately signed out | browsing over plain `http://` with `ENVIRONMENT=production`: finish step 8 (HTTPS), or set `COOKIE_SECURE=false` temporarily |
| A page reload on `/invoices/123` gives 404 | `FallbackResource` missing from the vhost, or `DocumentRoot` doesn't point at `frontend/dist` |
| Logo upload fails | `/var/lib/saumgm/storage` must be owned by `saumgm`; uploads are limited to 20 MB |
| PDFs show the wrong address | the remit-to address valid on the invoice date is used: Settings → Addresses, valid from/to |
| Apache errors | `/var/log/apache2/saumgm-error.log`; `sudo apache2ctl configtest` |
| Slow pages | Apache can log each request's duration: add `%D` (microseconds) to the `LogFormat` used by `saumgm-access.log`; check `SHOW PROCESSLIST` in MariaDB |

Health check for monitoring: `GET /api/health` returns 200 with `"database":"ok"` when the API can
reach the database.
