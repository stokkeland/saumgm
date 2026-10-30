# Running several SauMGM instances on one server

One server can run any number of independent SauMGM installations ("instances"), each in its own
folder with its own database, files, port, web address and backups. Typical uses:

- separate businesses (each instance is one business with its own users);
- a **demo** instance next to the real one (loaded with `python -m saumgm load-demo`);
- a **test** instance for trying a new version before updating production.

Instances share nothing but the server's packages (Python, Apache, MariaDB). Each one has its own
checkout of the code, so each can run a different version and be updated on its own.

Read [ubuntu.md](ubuntu.md) first: this guide reuses its steps and only lists what is different.

## Naming convention

Pick a short name per instance (letters `a-z`, digits and `-`), for example `acme`, `demo` or
`test`, and a free local port (8001, 8002, ...). The scripts and service templates in `deploy/`
derive everything else from the name:

| | Single instance (ubuntu.md) | Instance `NAME` |
|---|---|---|
| Code | `/opt/saumgm` | `/opt/saumgm-NAME` |
| Configuration | `/opt/saumgm/backend/.env` | `/opt/saumgm-NAME/backend/.env` |
| Port | 8000 | `PORT=` in `/etc/saumgm/NAME.env` |
| System user | `saumgm` | `saumgm-NAME` |
| Database / DB user | `saumgm` / `saumgm` | `saumgm_NAME` / `saumgm_NAME` (`-` becomes `_`) |
| Files | `/var/lib/saumgm/storage` | `/var/lib/saumgm-NAME/storage` |
| Backups | `/var/backups/saumgm` | `/var/backups/saumgm-NAME` |
| systemd service | `saumgm` | `saumgm@NAME` |
| Backup timer | `saumgm-backup.timer` | `saumgm-backup@NAME.timer` |
| Reminders digest timer | `saumgm-notify.timer` | `saumgm-notify@NAME.timer` |
| Apache site | `saumgm.conf` | `saumgm-NAME.conf` (from `saumgm-instance.conf`) |
| Logs | `journalctl -u saumgm` | `journalctl -u saumgm@NAME` |

An existing single instance keeps running as it is next to new named instances; there is no need
to convert it.

Keep a list of which port belongs to which instance; `grep PORT /etc/saumgm/*.env` shows it.

## Adding an instance

The example creates instance `acme` on port `8001`, reachable at `https://acme.example.com`.
Replace the three values throughout.

### 1. Packages, user and folders

Packages are installed once per server (ubuntu.md step 1). Then create the instance's system user
and folders:

```sh
sudo bash /opt/saumgm/deploy/install-prereqs.sh --instance acme
#   or, before any checkout exists, from a copy of the script anywhere
```

### 2. Database

```sh
sudo mariadb <<'SQL'
CREATE DATABASE saumgm_acme CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'saumgm_acme'@'localhost' IDENTIFIED BY 'CHANGE-ME';
GRANT ALL PRIVILEGES ON saumgm_acme.* TO 'saumgm_acme'@'localhost';
SQL
```

Each instance gets its own database user, so one instance can never read another's data.

### 3. Code

As in ubuntu.md section 3, the checkout belongs to your admin account, so git, `venv` and pip
run without `sudo`:

```sh
sudo install -d -o "$USER" -g "$USER" /opt/saumgm-acme
git clone --branch release/v2.0 https://github.com/stokkeland/saumgm.git /opt/saumgm-acme
cd /opt/saumgm-acme
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -e backend
```

Each instance can follow its own branch (a test instance could follow `main`, the next version).

### 4. Configuration

```sh
sudo tee /opt/saumgm-acme/backend/.env >/dev/null <<'EOF'
DATABASE_URL=mysql+pymysql://saumgm_acme:CHANGE-ME@127.0.0.1:3306/saumgm_acme?charset=utf8mb4
STORAGE_URL=file:///var/lib/saumgm-acme/storage
ENVIRONMENT=production
LOG_LEVEL=INFO
APP_URL=https://acme.example.com
CORS_ORIGINS=
EOF
sudo chown root:saumgm-acme /opt/saumgm-acme/backend/.env
sudo chmod 640 /opt/saumgm-acme/backend/.env

sudo install -d -m 755 /etc/saumgm
echo "PORT=8001" | sudo tee /etc/saumgm/acme.env
# optional: WORKERS=1 for a small demo or test instance (default 2)
```

`STORAGE_URL` must point inside `/var/lib/saumgm-acme`: the service may only write there.

### 5. Data

Run as the instance's user, from its folder. Choose one:

```sh
cd /opt/saumgm-acme/backend
sudo -u saumgm-acme .venv/bin/alembic upgrade head          # always first

# a) a new, empty business
sudo -u saumgm-acme .venv/bin/python -m saumgm create-organization --name "Acme Inc"
sudo -u saumgm-acme .venv/bin/python -m saumgm create-user --email you@example.com --name "You" --role owner

# b) existing data: load an export (ubuntu.md step 5, option A) into saumgm_acme instead
sudo mariadb --default-character-set=utf8mb4 saumgm_acme < /tmp/saumgm.sql

# c) the demo business (see "A demo instance" below)
sudo -u saumgm-acme .venv/bin/python -m saumgm load-demo
```

### 6. Frontend

Build it in the instance's own checkout (ubuntu.md step 6), so it matches that instance's API:

```sh
cd /opt/saumgm-acme/frontend && npm ci --no-audit --no-fund && npm run build     # as you, no sudo
```

### 7. Service

The template unit is installed once per server; then each instance is enabled by name:

```sh
sudo cp /opt/saumgm-acme/deploy/systemd/saumgm@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now saumgm@acme
curl -s http://127.0.0.1:8001/api/health
```

### 8. Apache and HTTPS

Each instance needs its own host name (for example a subdomain per business). Running instances
under paths of one host name (`example.com/acme/`) is not supported: the frontend expects to be
served from `/`.

```sh
sed -e 's/@NAME@/acme/g' -e 's/@PORT@/8001/g' -e 's/@HOST@/acme.example.com/g' \
    /opt/saumgm-acme/deploy/apache/saumgm-instance.conf \
    | sudo tee /etc/apache2/sites-available/saumgm-acme.conf
sudo a2ensite saumgm-acme
sudo apache2ctl configtest && sudo systemctl reload apache2
sudo certbot --apache -d acme.example.com
```

### 9. Backups

```sh
sudo chmod +x /opt/saumgm-acme/deploy/*.sh
sudo cp /opt/saumgm-acme/deploy/systemd/saumgm-backup@.service \
        /opt/saumgm-acme/deploy/systemd/saumgm-backup@.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now saumgm-backup@acme.timer
sudo systemctl start saumgm-backup@acme.service && ls -lh /var/backups/saumgm-acme
```

Backups use root's socket login by default. For a remote database, put its credentials in
`/etc/saumgm/acme-backup.cnf` (mode 600, same format as ubuntu.md step 9). The timer spreads the
instances' start times over 45 minutes so their dumps don't all run at once.

The daily reminders digest ([ubuntu.md, section 7](ubuntu.md#the-daily-reminders-digest)):

```sh
sudo cp /opt/saumgm-acme/deploy/systemd/saumgm-notify@.service \
        /opt/saumgm-acme/deploy/systemd/saumgm-notify@.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now saumgm-notify@acme.timer
```

## Updating

```sh
sudo /opt/saumgm-acme/deploy/update.sh --instance acme
```

Same steps as for the single instance (backup, pull, packages, migrations, frontend, restart, health
check), for that instance only. A good routine: update the `test` instance first, try it, then
update the others one at a time. To move an instance to a new version, add
`--branch release/vX.Y` after reading [../upgrading.md](../upgrading.md).

## A demo instance

A demo instance shows the app with made-up data and can be reset whenever needed. Use the steps
above with the name `demo` and `python -m saumgm load-demo` in step 5. The demo business, Maple
Ridge Tech, has 10 clients, 5 vendors, about 15 months of invoices, payments, deposits, expenses,
subscriptions, a sales-tax filing and contact documents, all dated relative to the day it was
loaded. It signs in with:

| Email | Role | Password |
|---|---|---|
| owner@example.com | owner | `saumgm-demo` |
| bookkeeper@example.com | bookkeeper | `saumgm-demo` |
| viewer@example.com | viewer | `saumgm-demo` |

The password is public, so never load the demo into an instance with real data, and change the
passwords (`python -m saumgm set-password`) if the demo is reachable from the internet.

To reset it to fresh demo data, for example after a presentation:

```sh
# Wipes instance "demo" completely. Check the name twice.
sudo systemctl stop saumgm@demo
sudo mariadb -e "DROP DATABASE saumgm_demo; CREATE DATABASE saumgm_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL PRIVILEGES ON saumgm_demo.* TO 'saumgm_demo'@'localhost';"
sudo find /var/lib/saumgm-demo/storage -mindepth 1 -delete
cd /opt/saumgm-demo/backend
sudo -u saumgm-demo .venv/bin/alembic upgrade head
sudo -u saumgm-demo .venv/bin/python -m saumgm load-demo
sudo systemctl start saumgm@demo
```

Why a loader script rather than an SQL file: the demo includes stored files (invoice PDFs, the
logo, receipts and documents) that an SQL dump would not carry, its dates would go stale, and the
script keeps working when the schema changes because it goes through the app's own code.

## Removing an instance

Take a last backup and keep it, then:

```sh
sudo systemctl disable --now saumgm@acme saumgm-backup@acme.timer saumgm-notify@acme.timer
sudo a2dissite saumgm-acme && sudo systemctl reload apache2
sudo certbot delete --cert-name acme.example.com
sudo mariadb -e "DROP DATABASE saumgm_acme; DROP USER 'saumgm_acme'@'localhost';"
sudo rm -r /opt/saumgm-acme /var/lib/saumgm-acme /etc/saumgm/acme.env
sudo userdel saumgm-acme
```

## Resources

Each uvicorn worker is a separate Python process using roughly 100 MB of memory. Two workers per
instance are plenty for a small business; `WORKERS=1` in `/etc/saumgm/NAME.env` suits demo and test
instances. MariaDB serves all instances from one server process, so its memory does not grow much
per instance.
