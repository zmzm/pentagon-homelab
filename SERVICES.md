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
| Coturn | TURN server | internal / configured externally | `apps/turn` | `data/turn` |

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

# Backups

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Backrest | Restic backup UI | `backrest.home.arpa` | `apps/backrest` | `data/backrest`, `backups/` |

---

# Messaging

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Matrix Synapse | Matrix homeserver | local port `127.0.0.1:8008` | `apps/matrix` | `data/matrix/synapse` |
| Matrix Postgres | Matrix database | internal | `apps/matrix` | `data/matrix/postgres` |

---

# External / Referenced Routes

| Route | Target | Notes |
|-------|-------|-------|
| `interview-assistant.home.arpa` | `nextapp:3000` | Present in Caddyfile; no local compose project is tracked in `apps/`. |

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

- All services are deployed via Docker Compose.
- Compose files live under `apps/`.
- Persistent data is stored under `data/`.
- Backup repositories are stored under `backups/`.
- Domains are routed through Caddy.
