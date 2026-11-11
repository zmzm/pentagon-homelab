# 🐳 Services

Inventory of tracked service definitions in the Pentagon homelab. This is configured
coverage, not a live health report; dated deployment evidence is linked separately.

---

# Core Infrastructure

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Caddy | Reverse proxy / TLS | `vault.home.arpa`, `docker.home.arpa`, `pihole.home.arpa`, `dashboard.home.arpa`, `backrest.home.arpa` | `apps/caddy` | `data/caddy` |
| Portainer | Docker management UI | `docker.home.arpa` | `apps/portainer` | `data/portainer` |
| Watchtower | Automatic container updates | internal | `apps/watchtower` | none |

---

# Network

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Pi-hole | DNS + ad blocker | `pihole.home.arpa` | `apps/pihole` | `data/pihole` |
| Pi-hole Adapter | Pi-hole summary API for Homepage and SmallTV | internal | `apps/pihole-adapter` | none |
| Unbound | Recursive DNS resolver | internal | `apps/unbound` | none |
| Cloudflared | Cloudflare tunnel | external tunnel | `apps/cloudflared` | `data/cloudflared` |

---

# Security

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Vaultwarden | Password manager | `vault.home.arpa` | `apps/vaultwarden` | `data/vaultwarden` |

---

# Dashboards

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Homepage | Service dashboard | `dashboard.home.arpa` | `apps/homepage` | `data/homepage` |

---

# Monitoring

A host systemd timer, `homelab-monitor.timer`, runs `scripts/monitor.py` every five minutes. It checks disk space, twelve managed containers, Matrix/Vaultwarden HTTP health, and Backrest backup results/freshness. Matrix alerts are active in the private, unencrypted **Server alerts** room, alongside local journal logging. This service is managed outside Docker Compose. Send `!status` in **Server alerts** for a fresh health report; a separate lightweight timer checks for authorized requests every 15 seconds. Matrix PostgreSQL dumps run hourly and are checked for freshness. Weekly isolated recovery verification is monitored too. The twelve configured container checks exclude the Hermes stack and SmallTV; independent external monitoring remains [deferred](monitoring/EXTERNAL_MONITORING.md). See [database backups](OPERATIONS.md#matrix-database-backups) and [monitoring setup](monitoring/README.md).

---

# Backups

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Backrest | Restic backup UI | `backrest.home.arpa` | `apps/backrest` | `data/backrest`, `backups/`; incomplete USB copy (I/O errors) |

---

# Messaging

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Matrix Synapse | Matrix homeserver | `matrix.pentagonlab.org` via Cloudflare Tunnel | `apps/matrix` | `data/matrix/synapse` |
| Matrix Postgres | Matrix database | internal | `apps/matrix` | `data/matrix/postgres` |

---

# Personal Agent

These components share `apps/hermes/docker-compose.yml` and publish no host
ports. Their source and persistent data are separate from the core services.

| Component | Purpose | Source | Data location |
| --- | --- | --- | --- |
| Hermes | Matrix conversation, CLI and conversational schedules | `apps/hermes` | `data/hermes` |
| Pentagon Gateway | Authenticated tool API, policy discovery, audit and approvals | `apps/pentagon-gateway` | `data/pentagon-gateway` |
| Homelab broker | Allowlisted Docker inspection, logs and restart execution | `apps/pentagon-gateway` | none |
| Matrix approval listener | Trusted approval verification, exact-action execution and sanitized planning-result attachments | `apps/pentagon-gateway` | `data/matrix-approvals` |
| FlowForge inspector | Read-only registered projects, catalogs, queue records, doctor and sync preview | `apps/flowforge/inspector.py` | None; native sources mounted read-only |
| FlowForge planning API | Planning around the existing workflow runner | `apps/flowforge` | `data/flowforge-api` |

`homelab_list_services` reports configured tool coverage from gateway policy,
which is a subset of the services documented here, not a live service or health
inventory. It returns identifiers and informational restart levels without
Docker configuration, secrets, host paths or environment variables. Existing
restart authorization and confirmation remain authoritative. See
[the API and operating guide](apps/hermes/README.md#service-discovery-and-rollout)
and [deployment verification](reports/2026-10-22-homelab-service-discovery.md).

The approval listener delivers complete concept/grounded Markdown plans from the
gateway-sanitized response using the existing Matrix account. Its state retains
plan text and delivery progress, including failed/uncertain uploads and bounded
text fallback. The 2026-10-23 rollout recreated only this listener; see
[delivery recovery](apps/hermes/README.md#planning-result-delivery) and
[rollout verification](reports/2026-10-23-flowforge-matrix-delivery.md).

---

# Matrix Calling Status

As of 2026-10-11, coturn is removed from Compose, local runtime configuration, and the Ansible app list. Synapse has no configured STUN/TURN endpoints. No MatrixRTC/LiveKit backend is deployed.

The home connection is behind CGNAT. Messaging continues through Cloudflare Tunnel; legacy calls may work directly, but there is no relay for calls that need one. Matrix runtime configuration is in ignored `data/matrix/synapse/homeserver.yaml`.

---

# External / Referenced Routes

| Route | Target | Notes |
|-------|-------|-------|
| `interview-assistant.home.arpa` | `nextapp:4000` | Present in Caddyfile; no local compose project is tracked in `apps/`. |

---

# Ports

| Port | Service |
|----|----|
| `80` | Caddy HTTP |
| `443` | Caddy HTTPS |
| `53` TCP/UDP | Pi-hole DNS on host networking |
| `8081` | Pi-hole web UI on host |
| `5335` | Unbound DNS on localhost |
| `8008` | Matrix Synapse on localhost |
| `8096` | SmallTV JSON feed, bound to `${SMALLTV_BIND_IP:-192.168.0.185}` |
| `9898` | Backrest inside Docker network; no host port |

---

# Secrets

Real `.env` files are ignored by Git. Tracked example files:

| File | Variables |
|-------|-------|
| `apps/matrix/.env.example` | `MATRIX_POSTGRES_PASSWORD` |
| `apps/pihole-adapter/.env.example` | `PIHOLE_BASE_URL`, `PIHOLE_PASSWORD`, `REQUEST_TIMEOUT`, `SUMMARY_CACHE_TTL` |
| `apps/portainer/.env.example` | `PORTAINER_HOMEPAGE_WIDGET_KEY` |
| `apps/hermes/.env.example` | Provider/Matrix settings and distinct gateway, approver, broker and FlowForge credentials; see the [Hermes configuration guide](apps/hermes/README.md#configuration-and-deployment) |

Runtime `.env` files are local prerequisites; their presence and contents are not
established by this inventory.

---

# Notes

- Application services use Docker Compose; lightweight monitoring uses a host systemd timer.
- Compose files live under `apps/`.
- Persistent data is stored under `data/`.
- Backup repositories are stored under `backups/`.
- Local service domains are routed through Caddy; public Matrix access uses Cloudflare Tunnel.

The eleven core Compose projects have Ansible deployment playbooks, including service-specific recovery prerequisites and post-deployment checks. The personal-agent stack uses the separate deployment procedure in the Hermes guide. Monitoring and database backup timers are managed by `ansible/scheduled-jobs.yml`. See [Ansible deployment and recovery](ansible/README.md).

---

# SmallTV JSON Dashboard

`apps/smalltv-dashboard/compose.yaml` defines the JSON feed on LAN port 8096.
It provides weather, host and Pi-hole cards to the SmallTV-Ultra at `192.168.0.106`;
its active feeds are `/clock.json` and `/dashboard.json` at `http://192.168.0.185:8096`. See the
[app guide](apps/smalltv-dashboard/README.md) and
[deployment record](apps/smalltv-dashboard/DEPLOYMENT.md).

The SmallTV now uses a custom `esp8266-dashboard` firmware and the
`homelab-five-screens` theme. It rotates Bialystok clock/weather (40 seconds),
then the original host/Pi-hole pages and the new services/backups pages
(20 seconds each). A host timer publishes an allowlisted monitoring summary
for the dashboard; existing checks and Matrix alerts are unchanged. Weather is refreshed from Open-Meteo every ten
minutes; see [app deployment](apps/smalltv-dashboard/DEPLOYMENT.md).

SmallTV native night mode blanks the screen from 23:00 to 07:00 Europe/Warsaw.
The dashboard also sends bounded red/yellow problem and green recovery overlays,
with persistent deduplication, six-hour reminders and matching quiet hours.
Notification readiness is exposed at `/notifications.json`; details and rebuild
steps are in [the app guide](apps/smalltv-dashboard/README.md).

Persistent notification state is stored in `data/smalltv-dashboard`. The host
exporter publishes its allowlisted status file under `/var/lib/smalltv-dashboard`,
mounted read-only by the container. This project has no Ansible deployment playbook.
