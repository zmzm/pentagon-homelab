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

# Personal Agent Discovery and Diagnosis

The Hermes personal-agent stack runs from `apps/hermes`. Use read-only
`homelab_list_services` to discover configured tool coverage when a service
identifier is unknown or available coverage is needed. It reads gateway
`policy.services`, returning only identifiers and restart levels; it does not
query Docker or establish running state, health or reachability. Restart levels
are informational and do not bypass authorization or confirmation. A genuinely
ambiguous request still needs an actual user choice before inspection; never
substitute a configured service silently.

From `apps/hermes`, verify the deployed native tool selection and read-only MCP
path without sending a Matrix message or making a model request:

```bash
docker compose exec -T hermes python - < ../../scripts/verify_hermes_tool_registration.py
docker compose exec -T hermes python - < ../../scripts/verify_hermes_mcp.py
```

The first check verifies nine personal MCP tools for CLI, Matrix and cron plus
the curated diagnosis skill. The second reads policy coverage and performs the
existing Vaultwarden inspection; it does not request a restart or approval.
See [API, authentication and targeted rollout steps](apps/hermes/README.md#service-discovery-and-rollout)
and [the verified deployment record](reports/2026-10-22-homelab-service-discovery.md).

Saved conversations can retain earlier instructions despite a Hermes restart.
Use a fresh user-controlled session when testing revised diagnosis behavior:
send standalone `!new`, choose **Approve Once** if prompted, and wait for its
confirmation. The operator must not confirm or send user events on the user's
behalf. This native session reset is separate from gateway restart approvals.

After documentation changes are committed, refresh and check the allowlisted
homelab knowledge snapshot using [the documented host commands](apps/hermes/README.md#homelab-documentation).
Documentation-only refreshes need no service restart. Keep service policies,
credentials, monitoring and existing production schedules unchanged.

## FlowForge planning results in Matrix

The trusted approval relay sends a deterministic completion notice and full
`concept-plan.md` / `grounded-plan.md` UTF-8 attachments from the gateway-sanitized
API response. Failed runs receive a short error-code notice. See
[the 2026-10-23 deployment record](reports/2026-10-23-flowforge-matrix-delivery.md)
for the fixture coverage and read-only rollout checks; this rollout did not run
a paid workflow or send live test attachments.

The durable delivery record is `workflowDelivery` in each prompt in
`data/matrix-approvals/matrix-approvals.json`. An incomplete delivery remains
`failed`, retaining all available sanitized plan text and a bounded text fallback.
Confirmed uploads retain their media URI; unconfirmed file/notice sends reuse the
same Matrix transaction. An upload left `uncertain` is held for operator review,
and failed delivery records are not pruned with successful prompts.

Stop the relay and back up its state before any manual recovery. Do not clear
uncertain upload claims without establishing whether Matrix accepted the upload.
Keep approval decisions, execution claims, the state volume and Matrix credentials
intact. Do not attach raw files from `data/flowforge-api`, or rerun paid planning
to repair result delivery. Follow [the targeted relay rollout and recovery procedure](apps/hermes/README.md#planning-result-delivery).
Documentation snapshot refreshes do not require restarting other services.

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
apps/hermes/.env

Tracked example files document required variables:

apps/matrix/.env.example
apps/portainer/.env.example
apps/hermes/.env.example

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

The earlier public check returned HTTP 403 on 2026-10-11. On 2026-10-19, Matrix deployment verified both local health and public client versions over trusted HTTPS; tunnel deployment also verified connector readiness and both existing public routes. Current public access is verified separately from local health. If a public failure recurs, inspect Cloudflare access rules and the connector alongside the origin. Deploy the restored connector with `ansible-playbook cloudflared.yml` from `ansible/`; see [tunnel recovery and checks](ansible/README.md#cloudflare-tunnel-deployment).

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

To also start Synapse from the restored configuration, signing key, media and database:

```bash
sudo python3 -B scripts/verify-backup.py --matrix-app
```

This option requires the host's `python3-yaml` package and installed Matrix images. It verifies the saved Compose environment matches the restored database password, initializes a fresh database from the logical dump, and starts the installed Synapse image against it. Only disposable configuration is adjusted for a loopback database connection, disabled statistics reporting and temporary console logging. The original server identity and signing key are retained. The database has no network; Synapse shares that container's loopback-only namespace, with no published ports or production mounts. Local health, client versions and server-key responses are checked, including a match to the restored signing key. Containers and restored files are removed afterwards. PostgreSQL is limited to 768 MiB memory/512 MiB database tmpfs; Synapse to 1536 MiB memory; both to one CPU. Review these limits as data grows.

The application test passed on 2026-10-19 using snapshot `1aac183d`; see [the Synapse rebuild report](reports/2026-10-19-synapse-rebuild.md). This proves isolated startup from that backup with installed images. It does not test replacement-host provisioning, authenticated client login/messaging, federation, media delivery or an external backup destination.

## Expanded application recovery checks

```bash
sudo python3 -B scripts/verify-backup.py --matrix-workflows --vaultwarden-app
```

These options also start recovered Vaultwarden and exercise disposable-account login, encrypted item write/read/sync, Matrix local messaging and authenticated media upload/download. Synthetic writes require an explicit test flag and loopback-only interfaces; all containers have no outside network or published ports. Only private restored copies are changed, then removed. Real user passwords are not needed, and existing encrypted user content is not decrypted. The expanded workflow passed directly and through the installed weekly service on 2026-10-21; see [the report](reports/2026-10-21-action-batch.md).

## Scheduled recovery verification

`homelab-recovery.timer` runs `--matrix-workflows --vaultwarden-app` verification every Sunday between 04:30 and 05:00 Europe/Warsaw, with catch-up after downtime. Install it with `ansible/scheduled-jobs.yml` after restoring the local repository and deploying Matrix. It uses the latest snapshot available when it runs; it does not create a fresh backup or access the deferred USB destination.

The wrapper `scripts/recovery_test.py` prevents overlapping scheduled runs and publishes an atomic result in `/var/lib/homelab-recovery/status.json`. The directory is root-only 0700 and results/logs are 0600. `latest.log` retains only the latest run. Successful routine runs send no chat message. Existing five-minute monitoring reports failure, a run lasting over 35 minutes, or no successful verification in eight days. Failed/interrupted runs retain the previous success time without being reported as successful.

The service allows 30 minutes, then requests interruption so recovery cleanup can run, with three further minutes before forced termination. It uses the shared `/tmp` namespace because the Docker daemon must see restored bind-mount paths; temporary restored directories are private. Host paths are read-only except temporary storage, private result state and the repository's lock directory. Abrupt power loss/forced termination can bypass cleanup: inspect and remove only identified `matrix-restore-test-*` / `synapse-restore-test-*` resources and their temporary restore paths after confirming no verifier is running. Monitoring detects an unfinished result as stuck.

```bash
systemctl list-timers homelab-recovery.timer
sudo systemctl start homelab-recovery.service
sudo cat /var/lib/homelab-recovery/status.json
sudo journalctl -u homelab-recovery.service -n 10 --no-pager
# Detailed output is private and may reference recovered files:
sudo less /var/lib/homelab-recovery/latest.log
```

Read-only health checks now include recovery verification, bringing the total to 18. Independent outage monitoring is a separate task: [external monitoring setup](monitoring/EXTERNAL_MONITORING.md).

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

Prefer `ansible-playbook scheduled-jobs.yml` from `ansible/` after restoring runtime prerequisites and starting Matrix. This also installs monitoring and the status listener; see [Ansible scheduled jobs](ansible/README.md#monitoring-and-database-backup-jobs). For manual installation:

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
