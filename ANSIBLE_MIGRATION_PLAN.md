# Ansible Migration Plan

Plan for moving the homelab toward repeatable Ansible-managed deployment while keeping Docker Compose as the service runtime.

---

# Current State

- Docker Compose is the source of truth for services under `apps/`.
- Persistent runtime data lives under `data/` and is not committed.
- Secrets live in local `.env` files and are not committed.
- Ansible baseline exists under `ansible/`.
- `ansible/site.yml` remains read-only preflight. `ansible/prepare.yml` adds host prerequisites, missing directories, and missing shared Docker networks; Homepage deployment is automated separately in `ansible/homepage.yml`; other Compose applications remain manual.
- Matrix public HTTP access uses Cloudflare Tunnel because the home connection is behind CGNAT.
- Coturn was removed on 2026-10-11; keep it out of directory creation and Compose deployment. Synapse has no configured STUN/TURN endpoints, and no MatrixRTC/LiveKit backend is deployed.
- Synapse and Cloudflare Tunnel configs currently live under ignored `data/`; restoring Compose files alone does not recreate those configs.

---

# Improvement Priorities

1. Verify recovery: test restoring backups into a separate directory and keep a backup copy outside this server.
2. Add lightweight alerts for failed backups, low disk space, and unavailable services. Checks, local journal alerts, and Matrix delivery to the private, unencrypted **Server alerts** room are active.
3. Extend Ansible to prepare the host and deploy Compose services consistently. Host preparation and Homepage deployment are implemented; other Compose services remain next.
4. Back up runtime secrets securely, then introduce Ansible Vault for reproducible secret rendering.
5. Add centralized logging or deployment automation when there is a practical need.

These priorities guide the implementation phases below. Priority 2 checks and Matrix delivery are installed and verified.

Priority 1 is partially verified; the user deferred the USB work after repeated failures: on 2026-10-11 the local repository passed a full integrity check and the latest snapshot passed a verified file restore plus Vaultwarden SQLite integrity checks. USB copying failed again after filesystem repair and switching ports: the device disconnected during writes. A reliable external destination remains outstanding; the USB copy is incomplete and unverified. Consistent hourly PostgreSQL dumps and an isolated restore from a new Backrest snapshot are now verified. A full Synapse application rebuild remains outstanding. See [the recovery report](reports/2026-10-11-backup-recovery.md).


Priority 1 database follow-up: `homelab-matrix-backup.timer` creates hourly consistent dumps, and monitoring alerts on missing/empty dumps or age over two hours. Snapshot `69ce6af6` passed verified file recovery, Vaultwarden integrity, and isolated Matrix database recovery (169 tables, 4 users, 6 rooms, 401 events). See [database backup operations](OPERATIONS.md#matrix-database-backups).

Priority 2: a five-minute systemd timer now checks disk space, twelve managed containers, Matrix and Vaultwarden HTTP health, and Backrest backup results/freshness. The original 16 checks passed; the database dump freshness check brings coverage to 17 checks. Alert changes, recoveries, and six-hour reminders go to local journal and the private, unencrypted Matrix **Server alerts** room. The existing `@homelab` bot sends alerts to `@vladjik`; failed deliveries are queued for retry. Send `!status` in **Server alerts** for a fresh health report; a separate lightweight timer checks for authorized requests every 15 seconds. See [monitoring setup](monitoring/README.md).

---

# Goal

Use Ansible to make the host reproducible:

- verify host prerequisites
- create required directories
- create Docker networks
- render safe local config files from templates
- deploy Compose apps in a predictable order
- keep secrets out of Git

Docker Compose remains the per-service runtime.

---

# Phase 1: Preflight Baseline

Status: done

Files:

- `ansible/ansible.cfg`
- `ansible/inventory.ini`
- `ansible/group_vars/homelab.yml`
- `ansible/site.yml`

Capabilities:

- local inventory for the `pentagon` host
- shared homelab paths
- Compose app list
- repository path check

Validation:

```bash
cd ~/Documents/homelab/ansible
ansible-playbook site.yml
```

---

# Phase 2: Host Prerequisites

Status: implemented in `roles/host_prerequisites`, called by `prepare.yml`. Existing package versions are preserved; Docker is ensured running and enabled. Docker apt repository setup remains a prerequisite on fresh hosts.

The role installs missing packages and verifies:

- Docker Engine
- Docker Compose plugin
- Git
- curl
- DNS tools
- btop
- restic

The role does not invoke Compose, restart Docker, or upgrade installed packages. Starting Docker on a fresh/stopped host can start containers with restart policies; on this server Docker was already active.

Validation:

```bash
docker version
docker compose version
git --version
restic version
```

---

# Phase 3: Directory Layout

Status: implemented in `roles/directory_layout`. Existing directory ownership and modes are preserved; files and symlinks in expected directory paths fail validation. Declared permissions apply only to newly created paths. Service-specific ownership requirements remain to be documented before deployment.

Required base directories:

- `data/`
- `backups/`
- per-service `data/*` directories

Initial directories to manage:

- `data/caddy`
- `data/cloudflared`
- `data/homepage`
- `data/matrix`
- `data/pihole`
- `data/portainer`
- `data/unbound`
- `data/vaultwarden`
- `data/backrest`
- `data/monitoring` (root-only)
- `data/matrix/database-backup` (root-only)

Do not change ownership recursively across existing runtime data until each service's ownership requirements are documented.

---

# Phase 4: Docker Networks

Status: implemented in `roles/docker_networks`. Existing bridge networks are validated and preserved with their container connections and IPAM settings; only missing networks are created.

Initial network:

- `proxy`

Uses `community.docker.docker_network_info` and `community.docker.docker_network`. Collection 4.7.0 is installed and pinned in `requirements.yml`.

Validation:

```bash
docker network inspect proxy
```

---

# Phase 5: Compose Deployment

Status: Homepage is implemented in `ansible/homepage.yml` and `roles/homepage`. It reuses the existing Compose definition, preserves restored runtime configuration, waits for container health, and checks the dashboard through DNS/Caddy with verified TLS. Other applications remain manual. Homepage syntax, preview, deployment, repeatability, and HTTPS health checks passed on 2026-10-11. Runtime config contents and permissions were unchanged.

Deploy apps with `community.docker.docker_compose_v2`.

Recommended deployment order:

1. `caddy`
2. `unbound`
3. `pihole`
4. `pihole-adapter`
5. `homepage`
6. `portainer`
7. `vaultwarden`
8. `backrest`
9. `matrix`
10. `cloudflared`
11. `watchtower`

Start with one low-risk app first, such as `watchtower` or `homepage`, then expand.

Validation:

```bash
docker ps
docker compose ps
```

---

# Phase 6: Secrets

Move secret rendering into Ansible Vault.

Candidate secrets:

- `MATRIX_POSTGRES_PASSWORD`
- `PORTAINER_HOMEPAGE_WIDGET_KEY`

Keep rendered `.env` files ignored by Git.

Validation:

```bash
git status --short --ignored
```

Confirm `.env` files remain ignored.

---

# Phase 7: Service Health Checks

Status: implemented for Homepage HTTPS through DNS/Caddy; other services remain outstanding.

Add Ansible post-deploy checks for important local routes.

Examples:

```bash
curl -k https://vault.home.arpa
curl http://dashboard.home.arpa
dig google.com
```

For Matrix, check `curl -fsS http://127.0.0.1:8008/health` locally and test `https://matrix.pentagonlab.org/_matrix/client/versions` separately through the public tunnel. A local health response does not verify the public route.

Prefer checks that match actual user access paths through Caddy, Pi-hole, and Cloudflare Tunnel.

---

# Phase 8: Backups and Recovery

Use Ansible to verify backup tooling and expected paths:

- Backrest container exists
- backup repository path exists
- Restic is installed
- latest snapshots can be listed

Do not automate destructive restore workflows until they are tested manually and documented.

---

# Phase 9: Remote Provisioning

After local Ansible is stable, add a separate SSH inventory for provisioning a new host.

Do not replace the current local inventory. Keep both:

- local inventory for operations on the current host
- SSH inventory for bootstrap or rebuild scenarios

Remote inventory should avoid committing private IPs or usernames if the repo is public.

---

# Guardrails

- Do not commit real `.env` files.
- Do not commit `data/` or `backups/`.
- Do not template service configs until the current static config is understood.
- Do not automate destructive restore or cleanup commands early.
- Prefer one small role or one service migration per commit.
- Validate each phase with a command that can be rerun safely.

---

# Next Commit Candidates

1. Extend Compose deployment to another service after documenting its runtime config and permissions. Homepage is complete.
2. Extend post-deploy health checks beyond Homepage.
3. Add Ansible Vault templates for one `.env` file.
4. Manage monitoring and database backup units through Ansible.

Host preparation validated on 2026-10-11: syntax, preview, two unchanged production runs, isolated missing-directory/network creation, and a repeat with no changes all passed. Temporary test resources were removed.

Host preparation commands and limits: [Ansible README](ansible/README.md).
