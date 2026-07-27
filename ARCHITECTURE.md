# 🏗 Homelab Architecture

Infrastructure overview for the Pentagon homelab.

---

# High Level Architecture

Clients access most HTTP services through Caddy on the shared `proxy` Docker network.

```text
Clients / browsers
        │
        ▼
      Caddy
        │
 ┌──────┼───────────────┬───────────────┬───────────────┬──────────────┐
 │      │               │               │               │              │
 ▼      ▼               ▼               ▼               ▼              ▼
Vaultwarden        Portainer        Homepage        Backrest        Pi-hole
(passwords)        (Docker UI)      (dashboard)     (backups)       (DNS UI)
```

`interview-assistant.home.arpa` is still present in the Caddyfile and points to `nextapp:3000`, but there is no local `apps/nextapp` compose project in this repository.

---

# DNS Architecture

```text
Clients
   │
   ▼
Pi-hole
   │
   ▼
Unbound
   │
   ▼
Internet DNS root servers
```

Pi-hole handles DNS filtering and local domain resolution. Unbound acts as the recursive resolver on `127.0.0.1:5335`.

---

# Service Layout

```text
homelab/
├── apps/
│   ├── backrest
│   ├── caddy
│   ├── cloudflared
│   ├── homepage
│   ├── matrix
│   ├── pihole
│   ├── pihole-adapter
│   ├── portainer
│   ├── turn
│   ├── unbound
│   ├── vaultwarden
│   └── watchtower
├── backups/
├── data/
└── incidents/
```

- `apps/` contains Docker Compose projects and static configuration.
- `data/` contains persistent service data mounted into containers.
- `backups/` contains local backup repositories.
- `incidents/` contains postmortems and troubleshooting notes.

`data/`, `backups/`, and real `.env` files are intentionally excluded from Git.

---

# Reverse Proxy Routing

```text
vault.home.arpa                → vaultwarden:80
docker.home.arpa               → portainer:9000
pihole.home.arpa               → 100.126.16.76:8081
interview-assistant.home.arpa  → nextapp:3000
dashboard.home.arpa            → homepage:3000
backrest.home.arpa             → backrest:9898
```

---

# Container Overview

```text
caddy           → reverse proxy
vaultwarden     → password manager
pihole          → DNS and ad blocking
pihole-adapter  → Homepage Pi-hole widget API adapter
unbound         → recursive DNS resolver
portainer       → Docker management UI
homepage        → service dashboard
backrest        → Restic backup UI
cloudflared     → Cloudflare tunnel
coturn          → TURN server
matrix-synapse  → Matrix homeserver
matrix-postgres → Matrix database
watchtower      → automated container updates
```

---

# Security Notes

- Internal TLS is handled by Caddy for configured routes.
- Vaultwarden is exposed through the reverse proxy.
- DNS queries are filtered by Pi-hole and resolved through Unbound.
- Docker services are split between the shared `proxy` network, service-specific networks, and host networking where required.
- Secrets live in ignored `.env` files next to the relevant compose projects.

---

# Future Architecture

Potential additions to the infrastructure:

- Monitoring stack
- Centralized logging
- Off-device backup replication
- Git remote and deployment workflow
