# Ansible Migration Plan

Plan for moving the homelab toward repeatable Ansible-managed deployment while keeping Docker Compose as the service runtime.

---

# Current State

- Docker Compose is the source of truth for services under `apps/`.
- Persistent runtime data lives under `data/` and is not committed.
- Secrets live in local `.env` files and are not committed.
- Ansible baseline exists under `ansible/`.
- `ansible/scheduled-jobs.yml` installs monitoring, the Matrix status listener, and hourly database backup scripts/configuration and systemd units; it preserves restored credentials and runtime state.
- `ansible/site.yml` remains read-only preflight. `ansible/prepare.yml` adds host prerequisites, missing directories, and missing shared Docker networks; All eleven declared Compose projects, including Cloudflare Tunnel, have dedicated deployment playbooks with service-specific recovery prerequisites and health checks.
- Matrix public HTTP access uses Cloudflare Tunnel because the home connection is behind CGNAT.
- Coturn was removed on 2026-10-11; keep it out of directory creation and Compose deployment. Synapse has no configured STUN/TURN endpoints, and no MatrixRTC/LiveKit backend is deployed.
- Synapse and Cloudflare Tunnel configs currently live under ignored `data/`; restoring Compose files alone does not recreate those configs.

---

# Improvement Priorities

1. Verify recovery: test restoring backups into a separate directory and keep a backup copy outside this server.
2. Add lightweight alerts for failed backups, low disk space, and unavailable services. Checks, local journal alerts, and Matrix delivery to the private, unencrypted **Server alerts** room are active.
3. Extend Ansible to prepare the host and deploy Compose services consistently. Host preparation and all eleven Compose project deployments are implemented and verified against the current host. A separate SSH inventory and target-identity preflight are implemented; fresh-host provisioning and a complete rebuild remain untested.
4. Back up runtime secrets securely, then introduce Ansible Vault for reproducible secret rendering. Portainer rendering and encrypted import tooling are implemented and fixture-tested; the user initialized the production Vault locally on 2026-10-19. Its encrypted header, mode 0600, and Git exclusion are verified; the user-provided production run confirms successful decryption, environment rendering, Compose deployment, and HTTPS API verification (`ok=15`, `changed=1`, `failed=0`).
5. Add centralized logging or deployment automation when there is a practical need.

These priorities guide the implementation phases below. Priority 2 checks and Matrix delivery are installed and verified.

Priority 1 is partially verified; the user deferred the USB work after repeated failures: on 2026-10-11 the local repository passed a full integrity check and the latest snapshot passed a verified file restore plus Vaultwarden SQLite integrity checks. USB copying failed again after filesystem repair and switching ports: the device disconnected during writes. A reliable external destination remains outstanding; the USB copy is incomplete and unverified. Consistent hourly PostgreSQL dumps and an isolated restore from a new Backrest snapshot are now verified. Isolated Synapse startup from a later snapshot passed on 2026-10-19; see [the application recovery report](reports/2026-10-19-synapse-rebuild.md). Replacement-host provisioning remains outstanding. See [the recovery report](reports/2026-10-11-backup-recovery.md).


Priority 1 database follow-up: `homelab-matrix-backup.timer` creates hourly consistent dumps, and monitoring alerts on missing/empty dumps or age over two hours. Snapshot `69ce6af6` passed verified file recovery, Vaultwarden integrity, and isolated Matrix database recovery (169 tables, 4 users, 6 rooms, 401 events). See [database backup operations](OPERATIONS.md#matrix-database-backups).

Priority 2: a five-minute systemd timer now checks disk space, twelve managed containers, Matrix and Vaultwarden HTTP health, and Backrest backup results/freshness. The original 16 checks passed; the database dump freshness check brings coverage to 17 checks. Alert changes, recoveries, and six-hour reminders go to local journal and the private, unencrypted Matrix **Server alerts** room. The existing `@homelab` bot sends alerts to `@vladjik`; failed deliveries are queued for retry. Send `!status` in **Server alerts** for a fresh health report; a separate lightweight timer checks for authorized requests every 15 seconds. See [monitoring setup](monitoring/README.md).

Scheduled-job provisioning is implemented and verified on 2026-10-19: `ansible/scheduled-jobs.yml` stages and validates all six units, installs versioned scripts/configuration, enforces private runtime permissions, reloads changed units, and enables all three timers. Production deployment changed only file/directory permissions (`changed=3` task groups); an unchanged repeat passed with `changed=0`, `failed=0`. Existing scripts, config, unit sources, and alert credential contents were verified unchanged. A fresh database dump succeeded with mode 0600, all 17 health checks passed, and all services reported successful latest runs. Missing recovery credentials were verified to stop installation before creating directories. All 17 existing regression tests passed. See [scheduled jobs](ansible/README.md#monitoring-and-database-backup-jobs).

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

Status: implemented in `roles/host_prerequisites`, called by `prepare.yml`. Existing package versions are preserved; Docker is ensured running and enabled. Official Docker repository/key setup is now automated for supported Debian/Ubuntu ARM64/AMD64 hosts; matching existing sources are preserved, conflicting packages/configuration are refused and installed package versions are pinned per run.

Docker bootstrap extension validated on 2026-10-21: production preview, deployment and repeat passed with `changed=0`, preserving package versions, daemon PID, container IDs and existing source/key files. Isolated Debian ARM64 and Ubuntu AMD64 apt roots passed fresh repository setup, repeatability, signing-key checks and signed package discovery. All 15 regression tests and 18 production health checks passed. Full new-host installation remains untested; see [the report](reports/2026-10-21-docker-bootstrap.md).

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

Status: Homepage is implemented in `ansible/homepage.yml` and `roles/homepage`. It reuses the existing Compose definition, preserves restored runtime configuration, waits for container health, and checks the dashboard through DNS/Caddy with verified TLS. Portainer is implemented in `ansible/portainer.yml` and `roles/portainer`, requires its restored database, and verifies its HTTPS API through DNS/Caddy. Additional implemented services are described below; All declared Compose projects now have deployment playbooks. Homepage validation passed on 2026-10-11. Portainer syntax, preview, deployment, repeatability (`changed=0`), and HTTPS API checks passed on 2026-10-19; its existing environment contents and image were preserved and `.env` permissions restricted to 0600.

Deploy apps with `community.docker.docker_compose_v2`.

Watchtower is implemented in `ansible/watchtower.yml` and `roles/watchtower`. Its configuration is entirely in the existing Compose definition; it has no persistent data or service secret to restore. The role requires the Docker socket and `proxy` network, validates Compose, waits for container health, and runs the built-in health-check command. Syntax, preview, deployment, and repeat passed on 2026-10-19 (`changed=0`, `failed=0`). Existing image, schedule, environment, mount, restart policy, and Compose contents were verified unchanged; all 17 production health checks passed. All declared Compose projects now have deployment playbooks.

Vaultwarden is implemented in `ansible/vaultwarden.yml` and `roles/vaultwarden`. It requires the restored database and signing key, checks SQLite integrity/schema read-only, verifies the Compose data bind matches the checked directory, and checks `/alive` plus the web vault through trusted HTTPS. Syntax, preview, deployment, and repeat passed on 2026-10-19 (`changed=0`, `failed=0`), preserving the image, environment, data mount, signing key, ownership, modes, and Compose definition. Disposable missing/invalid database and mismatched-mount fixtures were rejected before deployment. All 17 production health checks passed. This does not establish an authenticated login or a full recovery exercise. See [Vaultwarden deployment](ansible/README.md#vaultwarden-deployment).

Caddy is implemented in `ansible/caddy.yml` and `roles/caddy`. The role requires restored CA certificates/keys, validates configuration with persistent state mounted read-only, checks mounts and the external shared network, reconciles Compose, and gracefully reloads changed active configuration. A stale file bind forces recreation. Syntax, preview, deployment, and repeat passed on 2026-10-19 (`changed=0`, `failed=0`), including all six HTTPS routes. Existing image, ports, network ID, Caddyfile, and CA contents/permissions were preserved. Missing-key and invalid-config fixtures were rejected; isolated lifecycle checks verified reload and stale-bind handling. All 17 production health checks passed. See [Caddy deployment](ansible/README.md#caddy-deployment).

Pi-hole is implemented in `ansible/pihole.yml` and `roles/pihole`. It requires restored configuration, the saved API password hash, gravity and history databases, and generated DNS configuration. It checks gravity integrity read-only, rejects unexpected upstreams/enabled conditional forwarding, verifies host networking and mounts, and validates DNS syntax in a disposable container with read-only state. Syntax, preview and two live runs passed on 2026-10-19 (`changed=0`, `failed=0`): Unbound, Pi-hole public DNS and six local records over UDP/TCP, and the HTTPS admin page all passed. Existing image, host networking, shared memory, mounts, environment, DNS settings, password hash, TOML and ownership/modes were preserved. Five unsafe/missing/corrupt fixture cases were rejected before deployment. Authenticated API access through the adapter and all 17 production health checks passed. See [Pi-hole deployment](ansible/README.md#pi-hole-deployment).

Matrix is implemented in `ansible/matrix.yml` and `roles/matrix`. It requires an existing PostgreSQL 16 cluster, matching restored secrets, preserved server identity/signing key, logging config and media store. Native read-only config validation and an authenticated read-only schema/locale probe precede deployment; PostgreSQL is reconciled and verified before Synapse. World-writable Synapse secrets were restricted to 0600, its directory to 0700, and `.env` to 0600, preserving owners and contents. Production deployment changed only these permission groups (`changed=3`); repeat and final verification passed with `changed=0`, `failed=0`, including local and public APIs. Five recovery guards and isolated PostgreSQL schema/password cases passed; all 17 production health checks passed. A later isolated application startup from backup passed; see [the application recovery report](reports/2026-10-19-synapse-rebuild.md). See [Matrix deployment](ansible/README.md#matrix-deployment).

Cloudflare Tunnel is implemented in `ansible/cloudflared.yml` and `roles/cloudflared`, completing all eleven Compose deployment playbooks. Restored tunnel UUID/credential consistency, ingress syntax and exact Matrix rule selection are verified before startup. Configuration and credentials retain their contents/owners but use service GID 65532 with mode 0640 inside a 0750 directory; metrics/readiness is explicitly loopback-only. Production deployment changed those permissions and reconnected the existing tunnel (`changed=3`); repeat passed with `changed=0`, `failed=0`. Connector readiness, local Matrix health, public Matrix versions and the existing secondary public route passed. Five invalid recovery/routing fixture cases were rejected, and all 17 production health checks passed. No tunnel identity, Cloudflare account configuration or DNS records were changed. See [tunnel deployment](ansible/README.md#cloudflare-tunnel-deployment).

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

Portainer support is implemented: `import-portainer-vault.py` encrypts the existing key without writing another plaintext copy, and the Portainer role can render `.env` from `vault_portainer_homepage_widget_key`. Encrypted import, protected template output, private modes, overwrite refusal, and empty-key rejection passed with disposable fixtures on 2026-10-19. The production variables file was created locally by the user on 2026-10-19; its encrypted header, mode 0600, and Git exclusion are verified. The user-provided production run verified decryption and environment rendering, with Compose and HTTPS API checks passing (`ok=15`, `changed=1`, `failed=0`); only the environment template changed. On 2026-10-21 the local finish helper verified two production-Vault runs, both `ok=15`, `changed=0`, `unreachable=0`, `failed=0`. See [Vault operations](ansible/README.md#portainer-secret-recovery-with-ansible-vault).

Matrix support is also implemented: `import-matrix-vault.py` encrypts the existing password and the Matrix role optionally renders its private `.env` after matching restored Synapse credentials and authenticating an already running database. This does not rotate credentials. The user created the permanent encrypted Matrix variables file locally; user-provided output on 2026-10-21 confirms successful production decryption, environment rendering, database authentication and local/public API checks (`ok=32`, `changed=0`, `failed=0`). See [Matrix Vault operations](ansible/README.md#matrix-password-recovery-with-ansible-vault).

Managed secret variables:

- `MATRIX_POSTGRES_PASSWORD`
- `PORTAINER_HOMEPAGE_WIDGET_KEY`

Matrix validation on 2026-10-19: four importer tests and eight isolated recovery-guard/template cases passed. Preview and live deployment using a disposable encrypted Vault passed; only the `.env` format changed (`changed=1`). Repeat passed with `changed=0`, `failed=0`. Database password, running container identities/images, Synapse configuration and signing key were preserved; all 18 health checks passed. The test Vault and unlock file were removed. Follow-up on 2026-10-21: the user created the permanent Matrix Vault and supplied a successful production run (`ok=32`, `changed=0`, `unreachable=0`, `failed=0`). The permanent Vault deployment is now verified; its unlock password remains known only to the user.

Keep rendered `.env` files ignored by Git.

Validation:

```bash
git status --short --ignored
```

Confirm `.env` files remain ignored.

---

# Phase 7: Service Health Checks

Status: implemented for authenticated Matrix database/schema checks, local Synapse health/client API and public client API through Cloudflare, Pi-hole upstream/DNS/local-record checks over UDP/TCP plus trusted HTTPS administration, six Caddy HTTPS routes with restored CA trust, Homepage HTTPS, Portainer HTTPS API, Vaultwarden HTTPS health/web vault, Backrest HTTPS UI/history, Watchtower's built-in health check, Unbound UDP/TCP recursion, Pi-hole adapter health/authenticated summary, and connector readiness/public HTTP routing for Cloudflare Tunnel. Baseline deployment checks cover all declared projects; independent outage monitoring and complete recovery tests remain separate work.

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

Implemented on 2026-10-21: `inventory.ssh.example.yml` and read-only `remote-preflight.yml`, automatically imported by shared preflight for replacement-group hosts. The private `inventory.ssh.yml` is ignored by Git. See [remote preparation](ansible/REMOTE_PROVISIONING.md). Actual new-host provisioning and a complete recovery exercise remain untested.

Do not replace the current local inventory. Keep both:

- local inventory for operations on the current host
- SSH inventory for bootstrap or rebuild scenarios

Remote inventory should avoid committing private IPs or usernames if the repo is public.

Validation on 2026-10-21: real SSH tests against a disposable loopback listener passed for direct, preview and shared preflight with `changed=0`. Eight incorrect target/identity/trust cases were rejected. All seven importer/target-guard regression tests passed; the existing local preflight remained unchanged and all 18 production health checks passed. Temporary SSH resources were removed. A separate-machine provisioning/recovery exercise remains outstanding.

---

# Guardrails

- Do not commit real `.env` files.
- Do not commit `data/` or `backups/`.
- Do not template service configs until the current static config is understood.
- Do not automate destructive restore or cleanup commands early.
- Prefer one small role or one service migration per commit.
- Validate each phase with a command that can be rerun safely.

---


# Completed Autonomous Tasks — 2026-10-19

- [x] Automate Backrest deployment: require restored configuration/history/repository, verify repository credentials without logging them, verify mounts, wait for active operations, and check trusted HTTPS plus backup history. First deployment reconciled the existing image (`changed=1`); repeat and the final run with the idle guard passed unchanged. Missing recovery files are rejected before deployment.
- [x] Automate Unbound deployment: validate the read-only config in a disposable container, reuse the existing image, and verify recursive IPv4 answers over UDP and TCP. Preview and two live runs passed with `changed=0`; an invalid configuration was rejected before deployment.
- [x] Automate Pi-hole adapter deployment: validate restored settings, restrict `.env` to 0600, build on demand, and verify health plus authenticated Pi-hole statistics. Applied the patched image and environment permissions (`changed=2`); the default-policy repeat passed with `changed=0`. Missing `.env` is rejected before deployment.
- [x] Remove adapter authentication-token logging and sensitive exception details: deployed source matches the checkout, current container logs omit the password and old token-log patterns, and all three privacy regression tests passed inside the new image with networking disabled. Added a credential-free environment example and excluded local environment files from the build context.

All 17 production health checks passed after the batch. Backrest and Unbound retain their existing images and configuration; the adapter image was intentionally rebuilt for the logging fix. Service-specific instructions, prerequisites, permissions, and verification limits are recorded in [Ansible operations](ansible/README.md). This batch does not establish a full replacement-host rebuild, full repository integrity, or an external backup.

---

# Next Commit Candidates

1. Completed on 2026-10-19: isolated Synapse startup from snapshot `1aac183d`, with restored database, configuration, signing key and media; health, client API and signing-key checks passed with loopback-only networking. Production remained healthy and temporary resources were removed. See [the rebuild report](reports/2026-10-19-synapse-rebuild.md). Replacement-host provisioning and client messaging remain untested.
2. Implemented: weekly isolated recovery verification with private atomic results and failure/staleness monitoring; see [scheduled recovery operations](OPERATIONS.md#scheduled-recovery-verification).
3. Completed: Matrix Vault import and production deployment. On 2026-10-21 the user-provided run verified decryption of the permanent Matrix Vault and unchanged deployment (`ok=32`, `changed=0`, `failed=0`), including authenticated database and local/public API checks. See [Matrix Vault operations](ansible/README.md#matrix-password-recovery-with-ansible-vault).
4. Completed on 2026-10-21: separate SSH inventory template, Git exclusion for its private copy, and read-only replacement-host verification integrated with shared preflight. Target identity and prerequisites are checked before deployment on a replacement inventory. See [remote preparation](ansible/REMOTE_PROVISIONING.md). A complete rebuild on a separate machine remains untested.
5. Completed on 2026-10-21: automatic official Docker apt repository/key setup for supported Debian/Ubuntu ARM64/AMD64 hosts. A valid existing repository is preserved; duplicate/incompatible sources, signature bypass, unexpected keys and conflicting packages stop preparation. Requested installed versions are preserved. Repository creation and signed package discovery were verified in isolated apt roots; a full new-host package installation remains untested. OS/account/SSH setup, checkout transfer and actual replacement-host recovery remain separate steps.

Deferred by the user on 2026-10-19: independent outside monitoring (improvement #2). No external monitor is active; account creation and activation are no longer an active next step. Keep [the prepared setup](monitoring/EXTERNAL_MONITORING.md) for a possible future revisit. Weekly recovery verification remains active.

Host preparation validated on 2026-10-11: syntax, preview, two unchanged production runs, isolated missing-directory/network creation, and a repeat with no changes all passed. Temporary test resources were removed.

Host preparation commands and limits: [Ansible README](ansible/README.md).

# Authorized Action Batch — 2026-10-21

Current detailed status: [ACTION_LIST.md](ACTION_LIST.md). Managed Synapse and tunnel settings, adapter Vault support, expanded Matrix/Vaultwarden recovery workflows, and safe source/encrypted-backup staging are implemented and verified within the documented scope. Weekly recovery now includes both application workflows. All 45 regression tests and 18 health checks passed. The user completed `ansible/finish-vault-work.py` locally: permanent Synapse/adapter encrypted imports and two production runs each for managed Matrix, adapter and Portainer passed with `changed=0`, `failed=0`; the credential-free completion record and all 18 subsequent health checks confirm success. Full separate-host provisioning and existing-user encrypted-content recovery remain untested. See [the batch report](reports/2026-10-21-action-batch.md).
