# 🏠 Pentagon Homelab

Raspberry Pi 5 based self-hosted infrastructure managed with Docker Compose.

## Hardware

- Device: Raspberry Pi 5
- RAM: 16 GB
- OS: Raspberry Pi OS
- Storage:
  - NVMe (temporary)
  - SSD planned

---

# 📁 Repository Structure

```text
homelab/
├── apps/        # Docker Compose files and app configs
├── backups/     # local backup repositories, not committed
├── data/        # persistent service data, not committed
└── incidents/   # incident reports and troubleshooting notes
```

Tracked files are intended to be reproducible service definitions and documentation. Runtime state, backups, downloaded binaries, and real `.env` files are ignored by Git.

```text
apps/
├── backrest
├── caddy
├── cloudflared
├── homepage
├── matrix
├── netdata
├── pihole
├── pihole-adapter
├── portainer
├── turn
├── unbound
├── vaultwarden
└── watchtower
```

```text
data/
├── backrest
├── caddy
├── cloudflared
├── homepage
├── matrix
├── netdata
├── pihole
├── portainer
├── turn
├── unbound
└── vaultwarden
```

---

# 🐳 Services

## Reverse Proxy

### Caddy

Handles internal routing and TLS for selected services.

- Location: `apps/caddy`
- Data: `data/caddy`
- Network: `proxy`
- Public ports: `80`, `443`

Routes:

- `vault.home.arpa` → `vaultwarden:80`
- `docker.home.arpa` → `portainer:9000`
- `pihole.home.arpa` → `100.126.16.76:8081`
- `interview-assistant.home.arpa` → `nextapp:3000`
- `dashboard.home.arpa` → `homepage:3000`
- `backrest.home.arpa` → `backrest:9898`
- `netdata.home.arpa` → `netdata:19999`

---

## Backups

### Backrest

Restic backup UI.

- Location: `apps/backrest`
- Data: `data/backrest`
- Backup repositories: `backups/`
- Access: `http://backrest.home.arpa`

---

## Password Manager

### Vaultwarden

Bitwarden-compatible password manager.

- Location: `apps/vaultwarden`
- Data: `data/vaultwarden`
- Access: `https://vault.home.arpa`

---

## DNS & Network

### Pi-hole

Network-wide ad blocker and DNS manager.

- Location: `apps/pihole`
- Data: `data/pihole`
- Access: `http://pihole.home.arpa`
- Host web port: `8081`

Uses Unbound as upstream DNS resolver.

### Pi-hole Adapter

Small custom API adapter used by Homepage widgets.

- Location: `apps/pihole-adapter`
- Secrets: `apps/pihole-adapter/.env`
- Network: `proxy`

### Unbound

Recursive DNS resolver.

- Location: `apps/unbound`
- Config: `apps/unbound/unbound.conf`
- Port: `127.0.0.1:5335`

### Cloudflared

Cloudflare tunnel container.

- Location: `apps/cloudflared`
- Data/config: `data/cloudflared`
- Network mode: `host`

### Coturn

TURN server.

- Location: `apps/turn`
- Config/data: `data/turn`
- Network mode: `host`

---

## Docker Management

### Portainer

Docker management UI.

- Location: `apps/portainer`
- Data: `data/portainer`
- Access: `http://docker.home.arpa`
- Secrets: `apps/portainer/.env`

---

## Dashboards

### Homepage

Main service dashboard.

- Location: `apps/homepage`
- Config/data: `data/homepage`
- Access: `http://dashboard.home.arpa`

---

## Monitoring

### Netdata

Host and Docker monitoring agent connected to Netdata Cloud.

- Location: `apps/netdata`
- Data: `data/netdata`
- Access: `https://netdata.home.arpa` or Netdata Cloud
- Secrets: `apps/netdata/.env`

---

## Messaging

### Matrix Synapse

Matrix homeserver backed by Postgres.

- Location: `apps/matrix`
- Data: `data/matrix`
- Local Synapse port: `127.0.0.1:8008`
- Secrets: `apps/matrix/.env`

---

## Automation

### Watchtower

Automatic Docker image updater for containers with the Watchtower label enabled.

- Location: `apps/watchtower`
- Schedule: `0 0 4 * * *`

---

# 🔐 Secrets and Git

Real `.env` files are intentionally ignored. Example files document required variables:

- `apps/matrix/.env.example`
- `apps/portainer/.env.example`

Ignored sensitive/runtime paths include:

- `data/`
- `backups/`
- `apps/*/.env`
- `.agents/`
- `.codex/`
- downloaded binaries such as `cloudflared-linux-arm`

---

# 📋 Incidents

Operational issues and resolutions are documented in `incidents/`.
