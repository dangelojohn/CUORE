# AlfaCore Odoo 19 CE Installation Procedure — QNAP TS-851

**Document version:** v0.1
**Target hardware:** QNAP TS-851 (Intel Celeron J1800 dual-core 2.41 GHz, max 8 GB DDR3L, 8-bay SATA, 2× 1 GbE, QTS)
**Target software:** Odoo 19 CE in Docker, Postgres 16, Caddy reverse proxy
**Workflow:** This chat (planning + procedure authority) co-working with Claude Code (executes commands on the QNAP via SSH)
**Convention:** Each phase has Objective → Pre-checks → Commands → Verification → Checkpoint. Do not advance to the next phase until the checkpoint is signed off.
**Sign-off marker:** "Phase N complete — proceed" in chat, after Claude Code reports the verification step passing.

---

## Phase 0 — Reality check, discovery, and decisions

**Objective:** Confirm the actual hardware state of this specific TS-851 unit, document baseline configuration, and lock in the four open decisions that drive everything downstream.

**Decisions needed before any installs:**

1. **Installed RAM.** Stock unit is 1 GB; this will not work. Need confirmed 4 GB minimum, 8 GB strongly recommended. If unit currently has 1–2 GB, **stop and order a RAM upgrade kit** before proceeding. Use only QNAP-listed-compatible DDR3L SO-DIMMs.
2. **Storage profile.** Are the bays populated with SSDs or HDDs? Postgres performance on Odoo 19 is heavily I/O bound — at minimum, the volume that holds Postgres data needs to be SSD-backed. Acceptable patterns: (a) all-SSD pool, (b) SSD pool for Postgres/Odoo + HDD pool for backups/filestore archive, (c) HDD pool with QTS SSD-cache enabled (acceptable but inferior to a).
3. **Network access pattern.** Will Odoo be (a) LAN-only on the shop network, accessed via internal hostname/IP only, or (b) reachable from the public internet through a reverse proxy + TLS? LAN-only is simpler and is the recommended start; public exposure can be layered on later. Default: LAN-only for v0.1.
4. **Internet egress for image pulls.** The QNAP needs outbound HTTPS to Docker Hub (`registry-1.docker.io`, `auth.docker.io`, `production.cloudflare.docker.com`) to pull Odoo and Postgres images. If the firewall whitelists egress, those domains need to be allowed. Confirm before Phase 3.

**Discovery commands (Claude Code executes via SSH):**

```bash
# QTS firmware version
getcfg "System" "Version" -f /etc/config/uLinux.conf
getcfg "System" "Build Number" -f /etc/config/uLinux.conf

# Hardware model confirmation
getcfg "System" "Model" -f /etc/config/uLinux.conf
cat /proc/cpuinfo | grep -E "model name|cpu cores" | head -2

# Total RAM (the most important discovery)
free -h
cat /proc/meminfo | head -3

# Storage pools / volumes
df -h | grep -E "^/dev|Filesystem"
zpool list 2>/dev/null  # expected to fail on QTS — confirms not QuTS hero
ls -la /share/

# Container Station presence
ls /share/CACHEDEV1_DATA/.qpkg/container-station/ 2>/dev/null || echo "Container Station not installed"
/sbin/qpkg_cli --status container-station 2>/dev/null || true

# SSH user and shell
whoami
echo $SHELL

# Network interfaces and current IPs
ifconfig | grep -E "^[a-z]|inet " | head -20

# Internet egress test (without pulling anything yet)
curl -sI --max-time 10 https://registry-1.docker.io/v2/ | head -1
curl -sI --max-time 10 https://hub.docker.com | head -1
```

**Verification:**
- RAM ≥ 4 GB confirmed (8 GB strongly preferred).
- QTS firmware ≥ 5.x recommended (ideally latest stable 5.2.x line as of install date — verify with QNAP's release notes for TS-851).
- At least one storage volume mounted under `/share/`.
- SSH working as the admin user.
- Outbound HTTPS to Docker Hub returns HTTP responses (any 2xx/4xx is fine — confirms reachability).

**Checkpoint:**
Decisions 1–4 documented. RAM constraint resolved (no proceeding on <4 GB). Sign off: "Phase 0 complete — proceed."

---

## Phase 1 — QTS preparation and security baseline

**Objective:** Update QTS firmware to current stable, harden the QNAP-side surface, and establish a non-default admin path. The QNAP will be carrying business data soon — defaults are not acceptable.

**Steps (mostly QTS GUI work, some via SSH):**

1. **Firmware update via QTS GUI.** Control Panel → System → Firmware Update → Live Update. If a major version jump is shown, read release notes first (some major QTS upgrades on the TS-x51 line have had regressions; prefer point releases). Reboot when prompted.

2. **Disable services that aren't needed.** Control Panel → Network & File Services. Turn off: FTP, TFTP, Telnet, Web Server (port 80) if not needed, Multimedia Console, Photo Station, Music Station, Video Station, Surveillance Station, Plex, Download Station, Qsync. Keep on: SSH, SMB (only if needed for shop file shares), Container Station.

3. **Change the admin account.** Control Panel → Privilege → Users → create a new admin account with a non-`admin` username and a strong password. Then disable the default `admin` account. (Default `admin` is the #1 attack vector on internet-exposed QNAPs.)

4. **Enable 2FA on the admin account.** Control Panel → Privilege → Users → click the admin → 2-step verification.

5. **SSH hardening (via SSH command line):**

```bash
# Confirm SSH is listening on a known port — default is 22
netstat -tnlp 2>/dev/null | grep sshd || ss -tnlp | grep ssh

# Optional but recommended: change SSH port (avoids drive-by scanners)
# In QTS GUI: Control Panel → Network & File Services → Telnet/SSH → change "Port number"
# Pick a port in 49152–65535 range; record it.

# Verify auto-block is on for SSH
# Control Panel → System → Security → IP Access Protection
# Enable: SSH connection, threshold 5 unsuccessful attempts within 1 minute, block 1 hour

# Disable password auth for SSH if using key auth
# (Only do this AFTER successfully placing your SSH key in ~/.ssh/authorized_keys)
```

6. **NTP / time sync.** Control Panel → System → General Settings → Time. Set the timezone and enable NTP (pool.ntp.org is fine). Postgres timestamps and case audit trails depend on this being correct.

7. **System logging.** Control Panel → System → System Logs. Confirm logs are being written. Optionally configure Syslog forwarding if a central log collector exists.

**Verification:**
- Firmware version confirmed as latest stable for TS-851.
- Default `admin` account disabled.
- New admin account works with 2FA via SSH and GUI.
- SSH banner shows on connect; brute-force protection active.
- `date` command on the QNAP returns correct local time within 30 seconds of true.

**Checkpoint:**
QTS hardened. Sign off: "Phase 1 complete — proceed."

---

## Phase 2 — Storage planning and shared folders

**Objective:** Lay out the storage volumes and shared folders that the Odoo + Postgres containers will use. Get the layout right now; moving Postgres data later is painful.

**Layout (assumes 8 GB RAM TS-851 with at least 2 SSDs available):**

| Mount path | Purpose | Type | Approx size |
|---|---|---|---|
| `/share/CACHEDEV1_DATA/Container/odoo/` | Odoo project root (compose, configs, scripts) | SSD pool | 2 GB |
| `/share/CACHEDEV1_DATA/Container/odoo/postgres-data/` | Postgres data dir (mounted into pg container) | SSD pool | 50–200 GB depending on growth |
| `/share/CACHEDEV1_DATA/Container/odoo/odoo-data/` | Odoo filestore + sessions (mounted into Odoo container) | SSD pool | 20–100 GB depending on attachments |
| `/share/CACHEDEV1_DATA/Container/odoo/addons/` | Custom AlfaCore modules (bind-mounted into Odoo) | SSD pool | 1 GB |
| `/share/CACHEDEV1_DATA/Container/odoo/config/` | `odoo.conf`, `Caddyfile` | SSD pool | <100 MB |
| `/share/CACHEDEV1_DATA/Container/odoo/backups/` | Local backup staging (rotated to HDD pool nightly) | SSD pool | 20 GB |
| `/share/CACHEDEV2_DATA/Backups/odoo/` | Long-term backup retention | HDD pool | 200+ GB |

(`CACHEDEV1_DATA` and `CACHEDEV2_DATA` mount-point names depend on how you've created your storage pools in QTS — substitute the actual pool names. To list them: `ls /share/`.)

**Steps:**

1. **Create the shared folders via QTS GUI.** Control Panel → Privilege → Shared Folders → Create Shared Folder.
   - `Container` shared folder on the SSD pool (if not already present from Container Station install)
   - `Backups` shared folder on the HDD pool (for backup retention)
   - Set permissions so only the admin user has access; do NOT enable SMB/AFP/NFS for these folders unless there is a specific need.

2. **Create the Odoo project subdirectories via SSH:**

```bash
# Replace CACHEDEV1_DATA with your actual SSD pool path
PROJ=/share/CACHEDEV1_DATA/Container/odoo
mkdir -p $PROJ/{postgres-data,odoo-data,addons,config,backups,scripts,logs}

# Set ownership for Odoo's UID 101 (the Odoo container runs as UID 101)
# This is the #1 install gotcha — fix it now, not later
chown -R 101:101 $PROJ/odoo-data $PROJ/addons
# Postgres container runs as UID 999 by default in postgres:16 image
chown -R 999:999 $PROJ/postgres-data
# Config readable by both
chmod -R 755 $PROJ/config

# Verify
ls -la $PROJ
```

3. **Allocate the long-term backup target on the HDD pool:**

```bash
mkdir -p /share/CACHEDEV2_DATA/Backups/odoo/{daily,weekly,monthly}
```

4. **Verify SSD performance (sanity check, takes about 30 seconds):**

```bash
cd /share/CACHEDEV1_DATA/Container/odoo
dd if=/dev/zero of=test_write bs=1M count=512 conv=fdatasync 2>&1 | tail -1
dd if=test_write of=/dev/null bs=1M 2>&1 | tail -1
rm test_write
```

Expect ~200+ MB/s write and ~400+ MB/s read on a healthy SATA SSD. If you see <50 MB/s, investigate (cache warming, drive health) before continuing.

**Verification:**
- All directories created with correct ownership (UID 101 for Odoo dirs, UID 999 for Postgres dir).
- `df -h` shows healthy free space on the SSD pool (≥ 100 GB recommended for first year of operation).
- SSD throughput sanity-checked.

**Checkpoint:**
Storage layout confirmed. Sign off: "Phase 2 complete — proceed."

---

## Phase 3 — Container Station verification and Docker setup

**Objective:** Confirm Container Station is installed and at a recent version, verify Docker engine is reachable, and create the Docker network that Odoo and Postgres will share.

**Steps:**

1. **Install Container Station if not present.** App Center → search "Container Station" → install. Open it once via the GUI to accept the EULA and let it finish first-run initialization.

2. **Verify Docker version via SSH:**

```bash
# Container Station bundles Docker; the binary may be at one of these paths
which docker || ls -la /share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin/docker

# If not on PATH, add it for this session
export PATH=/share/CACHEDEV1_DATA/.qpkg/container-station/usr/bin:$PATH
docker --version
docker compose version
docker info | head -30
```

The Docker version on TS-851's Container Station may lag behind upstream Docker — that is acceptable as long as it is ≥ 20.10. If it is older than that, update Container Station first.

3. **Create the project Docker network:**

```bash
docker network create alfacore-net \
  --driver bridge \
  --subnet 172.30.0.0/24 \
  --opt com.docker.network.bridge.name=alfacore-br
docker network ls | grep alfacore
```

(Subnet chosen to avoid collision with QTS's default `bridge` 172.17.0.0/16 and any common LAN subnets like 192.168.x or 10.x.)

4. **Pre-pull the images (so Phase 7 + 8 don't stall on slow downloads):**

```bash
docker pull postgres:16
docker pull odoo:19
docker pull caddy:2
docker images | grep -E "postgres|odoo|caddy"
```

Expect roughly 1.2 GB total. If any pull fails, debug egress (Phase 0 verification).

**Verification:**
- `docker --version` reports ≥ 20.10.
- `docker network ls` shows `alfacore-net`.
- All three images present in `docker images`.

**Checkpoint:**
Docker stack is alive. Sign off: "Phase 3 complete — proceed."

---

## Phase 4 — Configuration files

**Objective:** Author the `odoo.conf`, the Postgres init parameters, the `docker-compose.yml`, and the `Caddyfile`. Get the configs committed to disk before bringing anything up.

### 4.1 `odoo.conf`

Worker count is the critical decision — TS-851's dual-core Celeron strongly limits parallelism. Formula `(cores × 2) + 1` would suggest 5, but with 8 GB total RAM and Postgres needing its share, a realistic count is **2 workers + 1 cron**. Anything more thrashes.

Create `/share/CACHEDEV1_DATA/Container/odoo/config/odoo.conf`:

```ini
[options]
; ===== Server =====
admin_passwd = REPLACE_WITH_STRONG_MASTER_PASSWORD
; (this is the master password used to manage databases via the /web/database/manager UI;
;  set it now, store it in a password manager — losing it locks you out of DB management)

; ===== Database =====
db_host = postgres
db_port = 5432
db_user = odoo
db_password = REPLACE_WITH_STRONG_DB_PASSWORD
db_maxconn = 32
list_db = True

; ===== Addons path =====
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons

; ===== Workers (tuned for 2-core CPU + 8GB RAM) =====
workers = 2
max_cron_threads = 1
limit_memory_soft = 1073741824    ; 1.0 GB per worker
limit_memory_hard = 1610612736    ; 1.5 GB per worker hard cap
limit_time_cpu = 600
limit_time_real = 1200
limit_request = 8192

; ===== Logging =====
log_level = info
log_handler = :INFO
logfile = /var/log/odoo/odoo.log
logrotate = True

; ===== Performance =====
proxy_mode = True               ; required because Caddy sits in front
xmlrpc = True
longpolling_port = 8072

; ===== Data dir =====
data_dir = /var/lib/odoo
```

Save with: `nano /share/CACHEDEV1_DATA/Container/odoo/config/odoo.conf`

Then fix ownership:
```bash
chown 101:101 /share/CACHEDEV1_DATA/Container/odoo/config/odoo.conf
chmod 640 /share/CACHEDEV1_DATA/Container/odoo/config/odoo.conf
```

### 4.2 Postgres tuning (passed in via compose `command:` rather than postgresql.conf)

Tuning targets for an 8 GB TS-851 where Postgres gets ~25% of RAM:
- `shared_buffers = 1GB`
- `effective_cache_size = 3GB`
- `work_mem = 16MB` (conservative for low RAM)
- `maintenance_work_mem = 128MB`
- `max_connections = 50`
- `wal_buffers = 16MB`

These values are passed in the compose file (Phase 4.4) so we can version-control them.

### 4.3 `Caddyfile`

Caddy handles HTTPS termination + gzip + websocket pass-through for Odoo's longpolling. For LAN-only initial install, we use Caddy's built-in TLS for the internal hostname (self-signed) and add real cert later when public exposure is decided.

Create `/share/CACHEDEV1_DATA/Container/odoo/config/Caddyfile`:

```
# Internal hostname — adjust to your LAN convention
# Example: alfacore.local, alfacore.lan, or the QNAP's IP
{
    auto_https off
}

:80, :443 {
    # For LAN-only install — Caddy uses an internal self-signed cert on 443
    tls internal

    # Static + most requests
    reverse_proxy odoo:8069 {
        header_up Host {host}
        header_up X-Real-IP {remote}
        header_up X-Forwarded-For {remote}
        header_up X-Forwarded-Proto {scheme}
    }

    # Longpolling channel (websocket) — separate upstream port
    @longpoll path /longpolling/* /websocket
    handle @longpoll {
        reverse_proxy odoo:8072
    }

    # Compression
    encode gzip

    # Reasonable upload size for Odoo attachments
    request_body {
        max_size 100MB
    }
}
```

When you move to public exposure later, replace `:80, :443 { tls internal }` with `your.domain.com {}` and Caddy will auto-issue a Let's Encrypt cert. That's a Phase 12 change, not now.

### 4.4 `docker-compose.yml`

Create `/share/CACHEDEV1_DATA/Container/odoo/docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    container_name: alfacore-postgres
    restart: unless-stopped
    networks:
      - alfacore-net
    environment:
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: REPLACE_WITH_STRONG_DB_PASSWORD
      POSTGRES_DB: postgres
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - /share/CACHEDEV1_DATA/Container/odoo/postgres-data:/var/lib/postgresql/data
    command: >
      postgres
      -c shared_buffers=1GB
      -c effective_cache_size=3GB
      -c work_mem=16MB
      -c maintenance_work_mem=128MB
      -c max_connections=50
      -c wal_buffers=16MB
      -c checkpoint_completion_target=0.9
      -c default_statistics_target=100
      -c random_page_cost=1.1
      -c effective_io_concurrency=200
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U odoo"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1.5G

  odoo:
    image: odoo:19
    container_name: alfacore-odoo
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - alfacore-net
    expose:
      - "8069"
      - "8072"
    environment:
      HOST: postgres
      USER: odoo
      PASSWORD: REPLACE_WITH_STRONG_DB_PASSWORD
    volumes:
      - /share/CACHEDEV1_DATA/Container/odoo/odoo-data:/var/lib/odoo
      - /share/CACHEDEV1_DATA/Container/odoo/config:/etc/odoo:ro
      - /share/CACHEDEV1_DATA/Container/odoo/addons:/mnt/extra-addons
      - /share/CACHEDEV1_DATA/Container/odoo/logs:/var/log/odoo
    command: ["odoo", "--config=/etc/odoo/odoo.conf"]
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8069/web/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 90s
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G

  caddy:
    image: caddy:2
    container_name: alfacore-caddy
    restart: unless-stopped
    depends_on:
      - odoo
    networks:
      - alfacore-net
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /share/CACHEDEV1_DATA/Container/odoo/config/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config
    deploy:
      resources:
        limits:
          memory: 256M

networks:
  alfacore-net:
    external: true

volumes:
  caddy-data:
  caddy-config:
```

**Save and validate:**
```bash
cd /share/CACHEDEV1_DATA/Container/odoo
docker compose config
# This parses the YAML and shows what Docker will actually launch.
# Errors here mean YAML syntax issues — fix before continuing.
```

**Replace the `REPLACE_WITH_STRONG_*` placeholders.** Use `openssl rand -base64 32` to generate two strong passwords. Update them in BOTH `odoo.conf` and `docker-compose.yml`. They MUST match.

**Verification:**
- `docker compose config` exits cleanly with no errors.
- All four config files exist with correct ownership.
- Master password and DB password are strong, unique, and stored in a password manager.

**Checkpoint:**
Configs committed. Sign off: "Phase 4 complete — proceed."

---

## Phase 5 — Bring up Postgres alone, verify, then Odoo

**Objective:** Stage the bring-up. Postgres first, healthcheck green, then Odoo, then Caddy. Catching errors at each layer is far easier than debugging a full-stack first launch.

**Steps:**

```bash
cd /share/CACHEDEV1_DATA/Container/odoo

# 1. Bring up Postgres only
docker compose up -d postgres
docker compose logs -f postgres
# Watch for: "database system is ready to accept connections"
# Ctrl-C out of logs once that line appears (container keeps running)

# 2. Verify healthcheck
docker compose ps
# postgres should show "healthy" within 30 seconds

# 3. Test connection from inside the network
docker run --rm --network alfacore-net postgres:16 \
  psql -h postgres -U odoo -d postgres -c "SELECT version();"
# Will prompt for password — enter the DB password

# 4. Bring up Odoo
docker compose up -d odoo
docker compose logs -f odoo
# Watch for: "HTTP service (werkzeug) running on ..."
# Ctrl-C out of logs

# 5. Verify Odoo is healthy
docker compose ps
# odoo should show "healthy" within ~2 minutes (start_period accounts for slow first boot)

# 6. Test Odoo from inside the network
docker run --rm --network alfacore-net curlimages/curl:latest \
  curl -sI http://odoo:8069/web/health
# Expect HTTP/1.1 200 OK

# 7. Bring up Caddy
docker compose up -d caddy
docker compose logs caddy
# Caddy logs should show it loaded the config and is serving

# 8. Final state check
docker compose ps
# All three containers: Up, healthy
```

**If any step fails:**
- Postgres won't start → check `/share/CACHEDEV1_DATA/Container/odoo/postgres-data` ownership (must be 999:999).
- Odoo can't connect to DB → check `db_password` matches in `odoo.conf` and `docker-compose.yml`; check `db_host = postgres` (the service name, not localhost).
- Odoo starts but UI throws 500 → check `/share/CACHEDEV1_DATA/Container/odoo/logs/odoo.log` and `/share/CACHEDEV1_DATA/Container/odoo/odoo-data` ownership (must be 101:101).
- Caddy fails to bind 80/443 → another QTS service is using those ports. Check QTS Web Server (Control Panel → Network & File Services → Web Server) — disable it, or move Caddy to 8443/8080.

**Verification:**
- All three containers `Up` and `healthy`.
- From a workstation on the LAN, browse to `https://<qnap-ip>` (accept the self-signed cert warning) — Odoo's database manager UI loads.
- The URL `https://<qnap-ip>/web/database/manager` shows the database creation form.

**Checkpoint:**
Bare Odoo 19 CE stack is live. Sign off: "Phase 5 complete — proceed."

---

## Phase 6 — Initial Odoo configuration

**Objective:** Create the first AlfaCore database, the admin user, the company record, and lock down the master password access.

**Steps:**

1. **Create the AlfaCore database via the web UI:**
   - Browse to `https://<qnap-ip>/web/database/manager`.
   - Click "Create Database".
   - Master password: the value you set in `odoo.conf` `admin_passwd`.
   - Database name: `alfacore` (or `alfacore_prod` — whichever convention you want long-term).
   - Email: the AlfaCore admin email.
   - Password: a strong password for the Odoo `admin` user (different from the master password).
   - Language: English (or your preferred — note: changing later is possible but messy).
   - Country: Canada.
   - Demo data: **unchecked** for production. (Check it only for a separate `_demo` database if you want to play.)

   Wait 2–5 minutes for initial DB provisioning. Slow on the J1800; this is normal.

2. **First login confirmation:**
   - You should be logged in as `admin` after creation.
   - Top-right → Settings → check Odoo version is `19.0`.

3. **Configure the company:**
   - Settings → Users & Companies → Companies → click the default company.
   - Rename to "AlfaCore" (or your formal entity name).
   - Address, phone, website, currency (CAD if Canadian-based), logo upload.

4. **Lock down list_db (after database creation):**

After the AlfaCore database is created, edit `/share/CACHEDEV1_DATA/Container/odoo/config/odoo.conf` and change:
```ini
list_db = False
dbfilter = ^alfacore$
```

This prevents the database manager from being publicly listed and forces requests to bind to the `alfacore` database only. Then restart Odoo:

```bash
cd /share/CACHEDEV1_DATA/Container/odoo
docker compose restart odoo
```

5. **Create the AlfaCore user accounts:**
   - Settings → Users & Companies → Users → Create.
   - For each named human user (Owner, Master Mechanic, Junior ×2, Knowledge Engineer, Accounting): create a user, assign initial groups (Settings/Administration: Settings or Access Rights only as appropriate). Detailed access control comes when AlfaCore custom modules are installed.
   - Activate two-factor authentication for the admin user immediately: top-right → My Profile → Account Security → Enable 2FA.

6. **Disable the demo public sign-up if accidentally enabled:**
   - Settings → General Settings → Permissions → "Customer Account" → set to "On invitation".

**Verification:**
- AlfaCore database exists and is the only DB visible (after `list_db = False`).
- Admin user can log in with 2FA.
- Company record reflects AlfaCore.
- 5–6 named users exist with appropriate base groups.

**Checkpoint:**
First-run config done. Sign off: "Phase 6 complete — proceed."

---

## Phase 7 — Backup baseline

**Objective:** Establish nightly Postgres dumps + filestore snapshots, with retention rotation. This is non-negotiable before any custom modules go in.

**Steps:**

1. **Create the backup script:**

Create `/share/CACHEDEV1_DATA/Container/odoo/scripts/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

PROJ=/share/CACHEDEV1_DATA/Container/odoo
BKP_LOCAL=$PROJ/backups
BKP_REMOTE=/share/CACHEDEV2_DATA/Backups/odoo
DATE=$(date +%Y%m%d-%H%M%S)
DAY_OF_WEEK=$(date +%u)   # 1=Monday ... 7=Sunday
DAY_OF_MONTH=$(date +%d)

# 1. Postgres dump (compressed, custom format for fast restore)
docker exec alfacore-postgres pg_dump -U odoo -Fc -f /tmp/alfacore-$DATE.dump alfacore
docker cp alfacore-postgres:/tmp/alfacore-$DATE.dump $BKP_LOCAL/
docker exec alfacore-postgres rm /tmp/alfacore-$DATE.dump

# 2. Filestore tar (Odoo attachments live here; pg_dump doesn't capture them)
tar czf $BKP_LOCAL/alfacore-filestore-$DATE.tar.gz \
  -C $PROJ/odoo-data filestore/alfacore 2>/dev/null || true

# 3. Tier rotation — copy to long-term backup pool
cp $BKP_LOCAL/alfacore-$DATE.dump $BKP_REMOTE/daily/
cp $BKP_LOCAL/alfacore-filestore-$DATE.tar.gz $BKP_REMOTE/daily/

# Sundays also go to weekly
if [ "$DAY_OF_WEEK" = "7" ]; then
  cp $BKP_LOCAL/alfacore-$DATE.dump $BKP_REMOTE/weekly/
  cp $BKP_LOCAL/alfacore-filestore-$DATE.tar.gz $BKP_REMOTE/weekly/
fi

# First of month also goes to monthly
if [ "$DAY_OF_MONTH" = "01" ]; then
  cp $BKP_LOCAL/alfacore-$DATE.dump $BKP_REMOTE/monthly/
  cp $BKP_LOCAL/alfacore-filestore-$DATE.tar.gz $BKP_REMOTE/monthly/
fi

# 4. Local cleanup — keep last 7 daily on SSD pool
find $BKP_LOCAL -name "alfacore-*.dump" -mtime +7 -delete
find $BKP_LOCAL -name "alfacore-filestore-*.tar.gz" -mtime +7 -delete

# 5. Remote retention — daily 30 days, weekly 12 weeks, monthly 12 months
find $BKP_REMOTE/daily -name "alfacore-*" -mtime +30 -delete
find $BKP_REMOTE/weekly -name "alfacore-*" -mtime +84 -delete
find $BKP_REMOTE/monthly -name "alfacore-*" -mtime +365 -delete

echo "[$(date)] Backup complete: $DATE"
```

```bash
chmod +x /share/CACHEDEV1_DATA/Container/odoo/scripts/backup.sh
```

2. **Test it manually:**

```bash
/share/CACHEDEV1_DATA/Container/odoo/scripts/backup.sh
ls -lh /share/CACHEDEV1_DATA/Container/odoo/backups/
ls -lh /share/CACHEDEV2_DATA/Backups/odoo/daily/
```

You should see two files (a .dump and a .tar.gz) in both locations.

3. **Schedule via QTS cron.** QTS uses a slightly nonstandard crontab path. The portable approach:

```bash
# Edit the QTS crontab
crontab -e
```

Add:
```
0 2 * * * /share/CACHEDEV1_DATA/Container/odoo/scripts/backup.sh >> /share/CACHEDEV1_DATA/Container/odoo/logs/backup.log 2>&1
```

Then make QTS persist the crontab across reboots (this is the QNAP-specific part — QTS rewrites `/etc/config/crontab` on boot from a saved copy):
```bash
crontab -l > /etc/config/crontab
/etc/init.d/crond.sh restart
```

4. **Test restore (the step everyone skips, that you must not):**

Restoring is the only proof a backup works. Do this on a throwaway test database:

```bash
# Copy the latest dump to a known location
DUMP=$(ls -t /share/CACHEDEV1_DATA/Container/odoo/backups/alfacore-*.dump | head -1)

# Create a test target DB
docker exec alfacore-postgres psql -U odoo -d postgres -c "CREATE DATABASE alfacore_restoretest;"

# Restore the dump into it
docker cp $DUMP alfacore-postgres:/tmp/restore.dump
docker exec alfacore-postgres pg_restore -U odoo -d alfacore_restoretest /tmp/restore.dump
docker exec alfacore-postgres psql -U odoo -d alfacore_restoretest -c "SELECT count(*) FROM res_users;"

# Cleanup
docker exec alfacore-postgres psql -U odoo -d postgres -c "DROP DATABASE alfacore_restoretest;"
docker exec alfacore-postgres rm /tmp/restore.dump
```

A non-zero `count(*)` means the restore worked.

**Verification:**
- Backup script runs to completion in under 60 seconds for an empty fresh DB.
- Files appear in both local and remote backup locations.
- Crontab persists after a QNAP reboot test.
- Restore-to-test-database succeeds.

**Checkpoint:**
Backups operational and tested. Sign off: "Phase 7 complete — proceed."

---

## Phase 8 — Operational baseline

**Objective:** Establish the day-to-day operational scripts and conventions before any custom AlfaCore module work begins.

**Steps:**

1. **Health check script.** Create `/share/CACHEDEV1_DATA/Container/odoo/scripts/health.sh`:

```bash
#!/bin/bash
echo "=== AlfaCore Odoo Stack Health ==="
echo "Time: $(date)"
echo
echo "--- Containers ---"
docker compose -f /share/CACHEDEV1_DATA/Container/odoo/docker-compose.yml ps
echo
echo "--- Disk ---"
df -h /share/CACHEDEV1_DATA /share/CACHEDEV2_DATA 2>/dev/null
echo
echo "--- Memory ---"
free -h
echo
echo "--- Postgres connection count ---"
docker exec alfacore-postgres psql -U odoo -d alfacore \
  -c "SELECT count(*) AS connections, state FROM pg_stat_activity GROUP BY state;" 2>/dev/null
echo
echo "--- Odoo log tail (last 20 lines) ---"
tail -20 /share/CACHEDEV1_DATA/Container/odoo/logs/odoo.log
```

```bash
chmod +x /share/CACHEDEV1_DATA/Container/odoo/scripts/health.sh
```

2. **Restart-stack and update-images scripts:**

`/share/CACHEDEV1_DATA/Container/odoo/scripts/restart.sh`:
```bash
#!/bin/bash
cd /share/CACHEDEV1_DATA/Container/odoo
docker compose restart "$@"
```

`/share/CACHEDEV1_DATA/Container/odoo/scripts/update-images.sh`:
```bash
#!/bin/bash
cd /share/CACHEDEV1_DATA/Container/odoo
echo "Pulling latest images..."
docker compose pull
echo "Stopping..."
docker compose down
echo "Starting with new images..."
docker compose up -d
echo "Done. Run health.sh to verify."
```

```bash
chmod +x /share/CACHEDEV1_DATA/Container/odoo/scripts/{restart.sh,update-images.sh}
```

3. **Document the master password recovery procedure.** Save somewhere outside the QNAP (password manager note):

> If the master password (`admin_passwd` in `odoo.conf`) is lost: SSH into QNAP, edit `/share/CACHEDEV1_DATA/Container/odoo/config/odoo.conf`, set new `admin_passwd`, then `docker compose restart odoo`. The new value takes effect immediately. The Odoo `admin` user password (different field) is recoverable via `docker exec` into Postgres and updating `res_users` directly — see Odoo official docs for the SQL.

4. **First-run reboot test.** Reboot the QNAP. Verify:
   - All three containers come back up automatically (`restart: unless-stopped`).
   - Crontab survives.
   - Odoo UI is reachable within 5 minutes of the reboot completing.

```bash
# Schedule the reboot (gives you 1 minute warning)
sudo reboot
# Wait ~5–8 minutes for full QTS boot + Container Station + Odoo
# Then SSH back in and run:
/share/CACHEDEV1_DATA/Container/odoo/scripts/health.sh
```

**Verification:**
- `health.sh` produces clean output with all containers healthy.
- Reboot test passes — system self-recovers.
- Backup cron survived the reboot.

**Checkpoint:**
Operational baseline complete. The Odoo 19 CE stack is production-ready (within the hardware envelope) and self-healing through routine reboots. Sign off: "Phase 8 complete — proceed."

---

## Phase 9 — Standard Odoo apps installation (foundation for AlfaCore modules)

**Objective:** Install the Odoo standard apps that AlfaCore custom modules will depend on, so the addons directory is unblocked when the first custom module ships.

**The standard apps that AlfaCore needs as dependency targets:**

| App | Purpose | Critical |
|---|---|---|
| Contacts | `res.partner` extensions | Yes |
| Fleet | Vehicle records FK target | Yes |
| Project | Service case parent | Yes |
| Inventory (Stock) | Parts & stock movements | Yes |
| Purchase | Supplier orders | Yes |
| Sales | Customer orders for storefront | Yes |
| Invoicing (Account) | Invoice flow | Yes |
| Knowledge | Procedure documentation | Yes |
| Discuss (Mail) | Chatter (auto-installed) | Auto |

**Install order matters** — install dependencies first.

**Steps (via Odoo web UI):**

1. **Apps menu → Update Apps List.** (Top-right gear icon → "Update Apps List".) This refreshes the catalog from the addons paths so anything you drop into `/mnt/extra-addons` later becomes installable.

2. **Install in this sequence, one at a time, waiting for each to complete:**

   - Contacts (usually pre-installed)
   - Fleet
   - Project
   - Inventory
   - Purchase
   - Sales
   - Invoicing
   - Knowledge

   For each: Apps → search the name → Activate. Wait 1–3 minutes per install on the J1800 (slower than typical hardware — be patient, do not click Install twice).

3. **Verify all installed:**

```bash
docker exec alfacore-postgres psql -U odoo -d alfacore \
  -c "SELECT name, latest_version, state FROM ir_module_module WHERE state = 'installed' ORDER BY name;" \
  | head -50
```

You should see the apps you installed plus their auto-installed dependencies.

**Verification:**
- All targeted apps show `state = installed`.
- Odoo UI navigation now shows Fleet, Project, Inventory, Purchase, Sales, Invoicing, Knowledge in the main app launcher.
- No errors in `/share/CACHEDEV1_DATA/Container/odoo/logs/odoo.log` after each install.

**Checkpoint:**
Standard app foundation in place. Sign off: "Phase 9 complete — proceed."

---

## Phase 10 — Addons directory readiness for AlfaCore custom modules

**Objective:** Confirm the `/mnt/extra-addons` mount works, the install/upgrade pipeline works, and document the workflow for adding the first custom module.

**Steps:**

1. **Test with a minimal stub module.** Create `/share/CACHEDEV1_DATA/Container/odoo/addons/alfacore_test/`:

```bash
ADDONS=/share/CACHEDEV1_DATA/Container/odoo/addons
mkdir -p $ADDONS/alfacore_test/{models,views,security}
```

Create `$ADDONS/alfacore_test/__manifest__.py`:

```python
{
    'name': 'AlfaCore Test Module',
    'version': '19.0.0.1.0',
    'summary': 'Sanity-check stub module for the AlfaCore addons pipeline',
    'category': 'AlfaCore',
    'author': 'AlfaCore',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
```

Create `$ADDONS/alfacore_test/__init__.py`:
```python
# Empty for stub — no models yet
```

Fix ownership (the install gotcha, again):
```bash
chown -R 101:101 $ADDONS/alfacore_test
chmod -R o+r $ADDONS/alfacore_test
```

2. **Refresh module list and install the stub:**

```bash
# Trigger a module list refresh (Odoo discovers new addons)
docker exec alfacore-odoo odoo -c /etc/odoo/odoo.conf -d alfacore \
  --stop-after-init --update list 2>&1 | tail -10
```

Then install via the Odoo web UI (Apps → Update Apps List → search "AlfaCore Test Module" → Activate), OR via CLI:

```bash
docker exec alfacore-odoo odoo -c /etc/odoo/odoo.conf -d alfacore \
  -i alfacore_test --stop-after-init 2>&1 | tail -20
```

(The CLI approach restarts Odoo's process; you'll need to bring the container back up afterward — `docker compose restart odoo`. The web-UI approach is preferred for normal operation.)

3. **Verify install:**

```bash
docker exec alfacore-postgres psql -U odoo -d alfacore \
  -c "SELECT name, state FROM ir_module_module WHERE name = 'alfacore_test';"
```

State should be `installed`.

4. **Now uninstall the stub** (so it's not lingering when real modules ship):
```bash
# Via web UI: Apps → search "AlfaCore Test" → click → Uninstall
# Or via CLI:
docker exec alfacore-odoo odoo -c /etc/odoo/odoo.conf -d alfacore \
  --stop-after-init --uninstall alfacore_test 2>&1 | tail
docker compose restart odoo

# Remove the stub directory
rm -rf $ADDONS/alfacore_test
```

5. **Document the standard custom-module deployment workflow** in `/share/CACHEDEV1_DATA/Container/odoo/scripts/deploy-module.sh`:

```bash
#!/bin/bash
# Usage: deploy-module.sh <module_name>
# Assumes module source is in $ADDONS/$1 and ownership is already correct.
set -euo pipefail
MODULE=${1:?Usage: $0 <module_name>}
ADDONS=/share/CACHEDEV1_DATA/Container/odoo/addons

if [ ! -d "$ADDONS/$MODULE" ]; then
  echo "Error: $ADDONS/$MODULE does not exist."
  exit 1
fi

echo "Fixing ownership..."
chown -R 101:101 $ADDONS/$MODULE
chmod -R o+r $ADDONS/$MODULE

echo "Refreshing apps list..."
docker exec alfacore-odoo odoo -c /etc/odoo/odoo.conf -d alfacore \
  --stop-after-init --update list 2>&1 | tail -5

echo "Installing/upgrading $MODULE..."
docker exec alfacore-odoo odoo -c /etc/odoo/odoo.conf -d alfacore \
  -u $MODULE --stop-after-init 2>&1 | tail -10

echo "Restarting Odoo..."
docker compose -f /share/CACHEDEV1_DATA/Container/odoo/docker-compose.yml restart odoo

echo "Done. Verify in UI: https://<qnap-ip>"
```

```bash
chmod +x /share/CACHEDEV1_DATA/Container/odoo/scripts/deploy-module.sh
```

**Verification:**
- Stub module installed and uninstalled cleanly.
- `deploy-module.sh` runs end-to-end without errors.
- Addons directory is empty and ready for first real module.

**Checkpoint:**
Custom module pipeline ready. Sign off: "Phase 10 complete — proceed."

---

## Final state summary

After all 10 phases complete, the AlfaCore Odoo 19 CE stack on this TS-851 is:

**Running:** Postgres 16, Odoo 19 CE, Caddy 2 — three containers, all healthy, on `alfacore-net` Docker bridge.

**Resourced:** Postgres capped at 2 GB RAM, Odoo at 4 GB RAM (2 workers + 1 cron), Caddy at 256 MB. Total ceiling ~6.5 GB on an 8 GB system, leaving ~1.5 GB headroom for QTS overhead.

**Persistent storage (SSD pool):**
- `/share/CACHEDEV1_DATA/Container/odoo/postgres-data/` — Postgres data dir
- `/share/CACHEDEV1_DATA/Container/odoo/odoo-data/` — Odoo filestore
- `/share/CACHEDEV1_DATA/Container/odoo/addons/` — custom modules
- `/share/CACHEDEV1_DATA/Container/odoo/config/` — odoo.conf, Caddyfile

**Backup:** Nightly Postgres dump + filestore tar at 02:00, rotated daily/weekly/monthly with retention 30/84/365 days, replicated to HDD pool. Restore tested.

**Access:** `https://<qnap-ip>/` — Caddy + self-signed internal cert, Odoo `proxy_mode = True`, longpolling routed to port 8072 internally.

**Standard apps installed:** Contacts, Fleet, Project, Inventory, Purchase, Sales, Invoicing, Knowledge (and their auto-installed dependencies).

**Custom modules:** None yet — addons pipeline tested with a stub. First AlfaCore custom module ships through `deploy-module.sh`.

---

## Hardware capacity flag

This TS-851 install is **viable for pilot, dev, and small-team early operation** — roughly 3–5 concurrent active users, light data volumes, single-shop scope. The dual-core J1800 and 8 GB RAM ceiling are genuine constraints. Indicators that you're outgrowing the hardware:

- Sustained Odoo response time > 2 seconds for routine page loads.
- Postgres `pg_stat_activity` shows queued/waiting connections regularly.
- Worker memory hits the 1.5 GB hard limit and gets killed mid-request (visible in `odoo.log` as `WORKER_LIMIT_MEMORY_HARD`).
- Backup duration creeps past 5 minutes.

When two of those four show up, plan a hardware migration — same Odoo stack, larger NAS or a dedicated Linux box. The compose file, configs, postgres data, and addons directory all migrate cleanly.

---

## Open items for next session

After Phase 10 sign-off, the next work item is the first AlfaCore custom module to install. Which one to start with depends on the answers to the open questions in the GAP analysis (case state machine, fleet-extended schema, etc.). Confirm priorities, then we author the manifest and code in Claude Code with this same phase-and-checkpoint discipline.

---

*End of v0.1 procedure. Update version on each material change. Save to `alfacore/docs/runbooks/odoo-install-ts851-v0.1.md` once the Forgejo organization exists.*
