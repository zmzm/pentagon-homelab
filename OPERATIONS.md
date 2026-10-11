# 🛠 Operations

Operational commands and troubleshooting guide for the Pentagon homelab.

---

# Docker Basics

## List running containers

docker ps

Show all containers (including stopped):

docker ps -a

---

## View container logs

Show logs:

docker logs CONTAINER_NAME

Follow logs live:

docker logs -f CONTAINER_NAME

Show last 100 lines:

docker logs --tail 100 CONTAINER_NAME

Example:

docker logs -f pihole

---

## Restart container

docker restart CONTAINER_NAME

Example:

docker restart pihole

---

## Stop container

docker stop CONTAINER_NAME

---

## Start container

docker start CONTAINER_NAME

---

# Docker Compose

All application compose files live in:

~/Documents/homelab/apps/

Example:

cd ~/Documents/homelab/apps/pihole

---

## Start services

docker compose up -d

---

## Stop services

docker compose down

---

## Restart services

docker compose restart

---

## Pull latest images

docker compose pull

---

## Recreate containers

docker compose up -d --force-recreate

---

# Ansible

Ansible is used as the migration path toward repeatable host setup and service deployment.

Current first step:

- Local inventory for the `pentagon` host
- Shared homelab paths and Compose app list
- Preflight playbook that verifies the repository path

Run the preflight:

sudo apt install ansible

cd ~/Documents/homelab/ansible
ansible-playbook site.yml

The playbook is intentionally read-only at this stage.

The first-step inventory uses `ansible_connection=local` because the playbook is currently run on the homelab host itself. Use a separate SSH inventory later when provisioning a different machine.

---

# Secrets

Real environment files are local only and ignored by Git.

Current local secret files:

apps/matrix/.env
apps/pihole-adapter/.env
apps/portainer/.env

Tracked example files document required variables:

apps/matrix/.env.example
apps/portainer/.env.example

When starting a service, run Docker Compose from that service directory so the local `.env` file is loaded automatically.

Example:

cd ~/Documents/homelab/apps/matrix
docker compose up -d

---

# Matrix

Matrix Synapse and Postgres are managed by `apps/matrix/docker-compose.yml`. Synapse listens on `127.0.0.1:8008`; `matrix.pentagonlab.org` reaches it through Cloudflare Tunnel using ignored `data/cloudflared/config.yml`. The Matrix server name is `pentagonlab.org`.

Runtime configuration and secrets:

- `data/matrix/synapse/homeserver.yaml`: Synapse configuration and application secrets; ignored by Git.
- `apps/matrix/.env`: database password; ignored by Git.
- `data/cloudflared/`: tunnel config and credentials; ignored by Git.

Check local health and containers:

```bash
curl -fsS http://127.0.0.1:8008/health
docker compose -f apps/matrix/docker-compose.yml ps
docker logs --tail 100 matrix-synapse
```

After editing `homeserver.yaml`, apply and verify:

```bash
docker restart matrix-synapse
# Allow Synapse to finish starting, then expect OK:
curl -fsS http://127.0.0.1:8008/health
```

Check the public route separately:

```bash
curl -fsS https://matrix.pentagonlab.org/_matrix/client/versions
docker logs --tail 100 cloudflared
```

The local health endpoint returned `OK` after the 2026-10-11 cleanup. The public versions endpoint returned HTTP 403 during the earlier check; public client access has not been verified by that local health check. If this persists, inspect the Cloudflare response and access rules alongside the tunnel logs.

## Calling status

The home connection is behind CGNAT. On 2026-10-11, the unused coturn Compose project, `data/turn/turnserver.conf` and its shared secret, Ansible app entry, and Google STUN entry in Synapse were removed. No coturn container existed at the time of removal. No STUN/TURN endpoints or MatrixRTC/LiveKit backend are configured.

Legacy clients can continue messaging. Calls may connect directly, but calls requiring a media relay will fail. The existing Matrix HTTP tunnel does not provide that relay. Reintroducing TURN would require a reachable public endpoint, such as an ISP-provided public IP or a VPS; a new domain purchase is unnecessary.

When restoring older backups, keep `apps/turn`, `data/turn`, and obsolete Synapse `turn_*` settings out of the active deployment unless a public relay has been deliberately configured.

---

# Backup Recovery Verification

Run the file recovery test from the repository root:

```bash
sudo python3 -B scripts/verify-backup.py --matrix-db
```

It restores the latest `pentagon-backup` snapshot into private temporary storage, verifies file contents, checks required recovery files and Vaultwarden SQLite integrity, and restores the saved Matrix dump into a temporary network-isolated PostgreSQL container. It removes the test container and temporary files afterwards. It never restores into production. This verifies database recovery but does not prove a complete Synapse application rebuild or external backup availability.

See [the 2026-10-11 recovery report](reports/2026-10-11-backup-recovery.md) for integrity-check results and remaining work. Keep the repository password in a secure location outside this server so recovery does not depend on its local Backrest configuration.

---

# Matrix Database Backups

`homelab-matrix-backup.timer` creates a consistent PostgreSQL custom-format dump hourly, with up to three minutes of scheduling delay and a catch-up run after boot. It uses `pg_dump` inside `matrix-postgres`; Synapse stays running. The latest complete dump is `data/matrix/database-backup/synapse.dump` (root-only directory 0700/file 0600). A failed dump keeps the previous complete copy. A lock prevents overlapping runs, and a validated temporary dump replaces the final file atomically.

Backrest already includes this directory through `/userdata/homelab`. Its daily snapshots preserve previous dump versions according to existing retention. The latest local dump normally limits database loss to roughly one hour; a daily Backrest snapshot may contain a dump roughly one day old, plus up to an hour of dump timing. Both copies currently share the server's storage. The raw live `data/matrix/postgres` files remain included but are not the verified database recovery source.

The monitor and `!status` check dump presence, size, and age; a missing/empty dump, a timestamp over five minutes in the future, or a dump older than two hours produces a critical alert. This freshness check does not revalidate the entire archive each run. Repeat the isolated restore test periodically and after database/image changes.

```bash
# Create a fresh dump through the installed service:
sudo systemctl start homelab-matrix-backup.service
sudo journalctl -u homelab-matrix-backup.service --since today
systemctl list-timers homelab-matrix-backup.timer

# Test the latest local dump in a disposable PostgreSQL container:
sudo python3 -B scripts/verify_matrix_db.py

# Test the newest Backrest snapshot including its database dump:
sudo python3 -B scripts/verify-backup.py --matrix-db
```

The isolated verifier reuses the running PostgreSQL image, creates a separate container with no network/host ports, no production mounts, and 512 MiB of temporary database storage. It restores in a single transaction, then checks Matrix schema and row counts. It does not start Synapse. Increase its explicit resource limits after reviewing database growth if the test database no longer fits.

For a real rebuild, restore the dump together with the corresponding Synapse configuration, signing key, media store, and Matrix `.env`. Compose recreates the `synapse` database role from the saved environment. The dump contains the single Synapse database, not cluster-wide roles/tablespaces; current Synapse uses its Compose-provisioned role and `plpgsql` only. Before a production restore, stop Synapse writes, prepare an empty database on a compatible PostgreSQL version, and review the target carefully. The supplied scripts intentionally perform test restores only.

To install the dump timer after rebuilding:

```bash
sudo install -d -m 0700 data/matrix/database-backup
sudo systemd-analyze verify monitoring/homelab-matrix-backup.service monitoring/homelab-matrix-backup.timer
sudo install -m 0644 monitoring/homelab-matrix-backup.service monitoring/homelab-matrix-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-matrix-backup.timer
sudo systemctl start homelab-matrix-backup.service
```

The unit's absolute paths match this host. Update them when moving the repository. References: [PostgreSQL consistent dumps](https://www.postgresql.org/docs/16/app-pgdump.html), [transactional restores](https://www.postgresql.org/docs/16/app-pgrestore.html).

---

# USB Backup Copy

**Current status:** USB copies failed both before and after approved filesystem repair and a move to USB 2. An explicitly authorized ext4 format attempt also stalled with repeated USB resets; formatting was not verified complete. The previous USB contents must be treated as erased; local safety copies remain in `data/usb-recovery/2026-10-11`. The device disconnected during writes, and the USB repository is incomplete and unverified. Do not rely on this drive for recovery. Use a different backup destination before retrying; see [the recovery report](reports/2026-10-11-backup-recovery.md#usb-copy-failure).

The PNY drive previously used exFAT UUID `E31C-6360`. The authorized format attempt invalidates that identity; the USB helper still contains the old UUID and must be updated only after a usable replacement filesystem is confirmed. The intended encrypted repository path is `homelab-backups/restic`. The copy uses the same password as Backrest repository `home-lab`; keep that password somewhere secure outside this server.

With the USB drive mounted, run from the repository root:

```bash
sudo python3 scripts/backup_usb.py
```

This copies snapshots from the local repository and skips snapshots already present. It identifies the mounted drive by UUID, refuses to copy if the expected drive is absent, and never prunes snapshots. Future copies are manual; no USB schedule is installed.

For a full USB integrity check after copying:

```bash
sudo python3 scripts/backup_usb.py --verify
```

Test recovery directly from the USB copy:

```bash
sudo env PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify-backup.py --usb
```

The initial repository creation uses `--initialize`; it is unnecessary for normal copies. USB repository contents are encrypted, including restored application secrets. Safely eject the drive before unplugging it. This is a separate storage device in the same location; an off-site copy remains future work.

---

# Git

The repository tracks service definitions, static configs, documentation, and incident notes.

Ignored local/runtime paths include:

data/
backups/
apps/*/.env
.agents/
.codex/
cloudflared-linux-arm

Check what would be committed:

git status --short

Check ignored files:

git status --short --ignored

---

# Inspect Docker

## Container details

docker inspect CONTAINER_NAME

---

## Show container resource usage

docker stats

---

## Show container networks

docker network ls

Inspect network:

docker network inspect NETWORK_NAME

---

# Disk Usage

## Docker disk usage

docker system df

---

## Clean unused images

docker image prune

---

## Clean everything unused

docker system prune

---

# Log Investigation

## Show system logs

journalctl -xe

---

## Follow system logs

journalctl -f

---

## Show service logs

journalctl -u SERVICE_NAME

Example:

journalctl -u docker

---

# DNS Troubleshooting

Used during DNS loop incident.

---

## Test DNS resolution

dig google.com

---

## Query specific DNS server

dig google.com @127.0.0.1 -p 5335

---

## Check Pi-hole DNS

dig google.com @PIHOLE_IP

---

## Test domain resolution

dig vault.home.arpa

---

## Trace DNS resolution

dig +trace google.com

---

# Network Diagnostics

## Check open ports

ss -tulnp

---

## Show listening services

netstat -tulnp

---

## Test connection

curl http://vault.home.arpa

---

## Check HTTP headers

curl -I http://vault.home.arpa

---

# File System Navigation

## List files

ls

Detailed list:

ls -lah

---

## Show directory tree

tree

Limit depth:

tree -L 3

---

# File Search

## Find files by name

find . -name "docker-compose.yml"

---

## Find directories

find . -type d -name "data"

---

# Text Search

## Search inside files

grep "vault.home.arpa" -R .

---

## Case insensitive search

grep -i "error" -R .

---

## Search logs for errors

grep -i error logfile.log

---

# Process Monitoring

## Show running processes

ps aux

---

## Filter processes

ps aux | grep docker

---

# System Monitoring

Automated checks run every five minutes through `homelab-monitor.timer`. Disk warnings start at 85% used; critical alerts start at 95% used or less than 2 GiB free. Failed/warning backups and successful backups older than 36 hours are reported alongside container and Matrix/Vaultwarden health problems. Alerts appear in local journal and the private, unencrypted Matrix room **Server alerts**. The bot `@homelab:pentagonlab.org` invited `@vladjik:pentagonlab.org`; accept the invitation to receive them. Failed deliveries retry on subsequent checks.

```bash
sudo journalctl -u homelab-monitor.service --since today
systemctl list-timers homelab-monitor.timer
sudo python3 -B scripts/monitor.py --check
```

Send `!status` in **Server alerts** for a fresh health report; a separate lightweight timer checks for authorized requests every 15 seconds. See [monitoring setup](monitoring/README.md) for configuration, installation, and coverage limits. Use `btop` and `df -h` for manual resource checks.

## CPU / Memory

top

Better alternative:

btop

---

## Disk usage

df -h

---

## Directory size

du -sh *

---

# Incident Investigation Workflow

Basic steps when something breaks:

1. Check containers

docker ps

2. Check logs

docker logs CONTAINER_NAME

3. Check DNS

dig google.com

4. Check reverse proxy

curl http://SERVICE_DOMAIN

5. Check ports

ss -tulnp

6. Check system logs

journalctl -xe

---

# Useful Paths

Homelab root:

~/Documents/homelab

Apps:

~/Documents/homelab/apps

Data:

~/Documents/homelab/data

Incidents:

~/Documents/homelab/incidents


# Ansible Host Preparation

Run from `ansible/` to load the repository configuration:

```bash
cd ~/Documents/homelab/ansible
ansible-playbook site.yml
ansible-playbook prepare.yml --check --diff
ansible-playbook prepare.yml
```

`site.yml` is read-only. `prepare.yml` uses sudo to install missing prerequisites, ensure Docker is running/enabled, and create missing directories/networks. It preserves existing directory permissions and network connections. It does not run Compose deployments or render secrets. See [Ansible usage and rebuild prerequisites](ansible/README.md).


## Deploy Homepage with Ansible

From `ansible/`:

```bash
ansible-playbook homepage.yml --check --diff
ansible-playbook homepage.yml
```

This deploys only the Homepage Compose project and verifies `https://dashboard.home.arpa` through DNS/Caddy with trusted local TLS. It requires restored Homepage configuration and the existing Caddy CA/network. Installed images are reused; changed configuration can recreate the container. See [Homepage deployment prerequisites](ansible/README.md#homepage-deployment).
