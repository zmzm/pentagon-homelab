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

`interview-assistant.home.arpa` is still present in the Caddyfile and points to `nextapp:4000`, but there is no local `apps/nextapp` compose project in this repository.

---

# Public Matrix Access

The home connection is behind CGNAT. Matrix HTTP traffic reaches Synapse through an outbound Cloudflare Tunnel:

```text
Matrix client → matrix.pentagonlab.org → Cloudflare → cloudflared → 127.0.0.1:8008 → Synapse → Postgres
```

The Matrix server name is `pentagonlab.org`; its public base URL is `https://matrix.pentagonlab.org/`. The tunnel route is stored in ignored `data/cloudflared/config.yml`. Matrix is separate from the Caddy routes below.

Coturn and its configuration were removed on 2026-10-11. Synapse has no configured STUN/TURN endpoints, and no MatrixRTC/LiveKit backend is deployed. Legacy calling relies on direct connectivity; a public relay would be needed for calls that cannot connect directly. The existing HTTP tunnel does not provide a TURN media relay.

---

# Personal Agent

Hermes uses GLM and Matrix through outbound connections. CLI, Matrix and cron
share an explicit personal MCP tool selection:

```text
Hermes → MCP stdio bridge → gateway → Knowledge Router / FlowForge planning API / read-only FlowForge inspector
                                  └→ isolated Docker broker (inspect/log/restart)
```

Service discovery stops at the gateway: `homelab_list_services` reads only
`policy.services` and returns configured identifiers and restart levels. It does
not contact the broker or Docker and makes no claim about running or healthy
services. Restart levels are informational; the existing gateway policy and
trusted approval process still decide whether a requested restart may execute.
The diagnosis skill discovers coverage when needed and requires the user to
resolve genuinely ambiguous targets.

The trusted Matrix approval listener polls the approved planning run through the
gateway, then sends one deterministic completion notice and full UTF-8 Markdown
attachments from the sanitized response. It never reads raw FlowForge output
files or calls a model to summarize plans. Its durable state stores sanitized
contents, upload claims, media URIs and event acknowledgments; uncertain uploads
stop for review, while message retries reuse stable Matrix transactions.
Incomplete delivery retains a failure record and bounded text fallback. See
[delivery and recovery](apps/hermes/README.md#planning-result-delivery).

The stack is deployed through `apps/hermes/docker-compose.yml` without published
host ports. Only the broker has a Docker socket; Hermes cannot reach its
operations network, and the gateway has no internet egress. See
[components and boundaries](apps/hermes/README.md#components-and-boundaries) and
[service discovery deployment](reports/2026-10-22-homelab-service-discovery.md).

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
│   ├── flowforge
│   ├── pentagon-gateway
│   ├── hermes
│   ├── homepage
│   ├── matrix
│   ├── pihole
│   ├── pihole-adapter
│   ├── portainer
│   ├── unbound
│   ├── vaultwarden
│   └── watchtower
├── backups/
├── data/
└── incidents/
```

- `apps/` contains Docker Compose projects and static configuration.
- `data/` contains persistent service data mounted into containers.
- `backups/` contains the local Restic repository. A separate encrypted repository was initialized on the PNY USB drive under `homelab-backups/restic`, but its first copy was interrupted by USB I/O errors and is unverified; see [USB backup operations](OPERATIONS.md#usb-backup-copy).
- `incidents/` contains postmortems and troubleshooting notes.

`data/`, `backups/`, and real `.env` files are intentionally excluded from Git.

---

# Reverse Proxy Routing

```text
vault.home.arpa                → vaultwarden:80
docker.home.arpa               → portainer:9000
pihole.home.arpa               → 100.126.16.76:8081
interview-assistant.home.arpa  → nextapp:4000
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
matrix-synapse  → Matrix homeserver
matrix-postgres → Matrix database
watchtower      → automated container updates
```

---

# Lightweight Monitoring

The host timer `homelab-monitor.timer` runs a short-lived Python checker every five minutes. It reads Docker status, calls Matrix/Vaultwarden health endpoints, checks root disk space, and queries Backrest backup history over its private Docker address. State changes, recovery, and six-hour reminders are logged to journald and sent by the existing Matrix bot to a private, unencrypted **Server alerts** room. Failed deliveries persist in a queue and retry on subsequent runs. State persists under `/var/lib/homelab-monitor`. Send `!status` in **Server alerts** for a fresh health report; a separate lightweight timer checks for authorized requests every 15 seconds. Matrix PostgreSQL dumps run hourly and are checked for freshness. See [database backups](OPERATIONS.md#matrix-database-backups) and [monitoring setup](monitoring/README.md).

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

- Centralized logging
- Off-device backup replication
- Git remote and deployment workflow

---

# SmallTV Desk Display

SmallTV-Ultra at `192.168.0.106` runs custom smalltv-mod 3.1.0-homelab.1 and polls the
`smalltv-dashboard` JSON service at `192.168.0.185:8096` every ten seconds.
The Compose service in `apps/smalltv-dashboard` uses the shared `proxy` network
for the existing Pi-hole adapter and read-only host metrics. Weather, host
metrics and Pi-hole use their original layouts alongside a separate clock/weather screen. Rendering
happens on the device from JSON; no dashboard screenshots are generated.
See [deployment and verification](apps/smalltv-dashboard/DEPLOYMENT.md).

The SmallTV now uses a custom `esp8266-dashboard` firmware and the
`homelab-five-screens` theme. Its `/clock.json` and `/dashboard.json` feeds
rotate Bialystok clock/weather (40 seconds), then host, Pi-hole, services and
backups (20 seconds each). The original layouts and 24-pixel weather date
are retained. A separate thirty-second exporter publishes an allowlisted
summary from the existing private five-minute monitoring state. Weather is refreshed from Open-Meteo every ten
minutes; see [app deployment](apps/smalltv-dashboard/DEPLOYMENT.md).

SmallTV native night mode blanks the screen from 23:00 to 07:00 Europe/Warsaw.
The dashboard also sends bounded red/yellow problem and green recovery overlays,
with persistent deduplication, six-hour reminders and matching quiet hours.
Notification readiness is exposed at `/notifications.json`; details and rebuild
steps are in [the app guide](apps/smalltv-dashboard/README.md).
