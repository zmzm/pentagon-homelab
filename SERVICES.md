# 🐳 Services

List of all services running in the Pentagon homelab.

---

# Core Infrastructure

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Caddy | Reverse proxy / TLS | — | apps/caddy | data/caddy |
| Portainer | Docker management UI | docker.home.arpa | apps/portainer | data/portainer |

---

# Network

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Pi-hole | DNS + Ad blocker | pihole.home.arpa | apps/pihole | data/pihole |
| Unbound | Recursive DNS resolver | internal | apps/unbound | data/unbound |

---

# Security

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Vaultwarden | Password manager | vault.home.arpa | apps/vaultwarden | data/vaultwarden |

---

# Dashboards

| Service | Purpose | Domain | App Location | Data Location |
|-------|-------|-------|-------|-------|
| Homarr | Main dashboard | dash.home.arpa | apps/homarr | data/homarr |
| Homepage | Secondary dashboard | SERVER_IP:3002 | apps/homepage | data/homepage |

---

# Applications

| Service | Purpose | Domain | Container |
|-------|-------|-------|-------|
| Interview Assistant | Next.js application | interview-assistant.home.arpa | nextapp |

---

# Ports

| Port | Service |
|----|----|
| 80 | Caddy |
| 443 | Caddy |
| 3002 | Homepage |
| 5335 | Unbound |

---

# Notes

- All services are deployed via Docker Compose.
- Compose files live in `apps/`.
- Persistent data is stored in `data/`.
- Domains are routed through Caddy.
