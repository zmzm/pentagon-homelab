# 🐳 Services

List of services in the Pentagon homelab.

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
| Pi-hole Adapter | Homepage widget API adapter | internal | `apps/pihole-adapter` | none |
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

A host systemd timer, `homelab-monitor.timer`, runs `scripts/monitor.py` every five minutes. It checks disk space, twelve managed containers, Matrix/Vaultwarden HTTP health, and Backrest backup results/freshness. Matrix alerts are active in the private, unencrypted **Server alerts** room, alongside local journal logging. This service is managed outside Docker Compose. Send `!status` in **Server alerts** for a fresh health report; a separate lightweight timer checks for authorized requests every 15 seconds. Matrix PostgreSQL dumps run hourly and are checked for freshness. See [database backups](OPERATIONS.md#matrix-database-backups) and [monitoring setup](monitoring/README.md).

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
| `8081` | Pi-hole web UI on host |
| `5335` | Unbound DNS on localhost |
| `8008` | Matrix Synapse on localhost |
| `9898` | Backrest inside Docker network |

---

# Secrets

Real `.env` files are ignored by Git. Tracked example files:

| File | Variables |
|-------|-------|
| `apps/matrix/.env.example` | `MATRIX_POSTGRES_PASSWORD` |
| `apps/portainer/.env.example` | `PORTAINER_HOMEPAGE_WIDGET_KEY` |

Existing ignored local env files:

- `apps/matrix/.env`
- `apps/pihole-adapter/.env`
- `apps/portainer/.env`

---

# Notes

- Application services use Docker Compose; lightweight monitoring uses a host systemd timer.
- Compose files live under `apps/`.
- Persistent data is stored under `data/`.
- Backup repositories are stored under `backups/`.
- Local service domains are routed through Caddy; public Matrix access uses Cloudflare Tunnel.

Homepage deployment is managed through `ansible/homepage.yml`, including container health and HTTPS dashboard verification. See [Ansible deployment](ansible/README.md#homepage-deployment).
