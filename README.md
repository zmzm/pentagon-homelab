# 🏠 Pentagon Homelab

Raspberry Pi 5 based self-hosted infrastructure managed with Docker Compose.

<img width="1672" height="941" alt="homelab (1)" src="https://github.com/user-attachments/assets/9270ed03-cd07-43aa-a3db-a129b7234910" />


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
├── ansible/    # host inventory and deployment automation
├── apps/        # Docker Compose files and app configs
├── backups/     # local backup repositories, not committed
├── data/        # persistent service data, not committed
└── incidents/   # incident reports and troubleshooting notes
```

Tracked files are intended to be reproducible service definitions and documentation. Runtime state, backups, downloaded binaries, and real `.env` files are ignored by Git.

```text
ansible/
├── ansible.cfg
├── group_vars/
│   └── homelab.yml
├── inventory.ini
└── site.yml
```

```text
apps/
├── backrest
├── caddy
├── cloudflared
├── homepage
├── matrix
├── pihole
├── pihole-adapter
├── portainer
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
├── pihole
├── portainer
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
- Host ports: `80`, `443` (home connection is behind CGNAT)

Routes:

- `vault.home.arpa` → `vaultwarden:80`
- `docker.home.arpa` → `portainer:9000`
- `pihole.home.arpa` → `100.126.16.76:8081`
- `interview-assistant.home.arpa` → `nextapp:4000`
- `dashboard.home.arpa` → `homepage:3000`
- `backrest.home.arpa` → `backrest:9898`

---

## Backups

### Backrest

Restic backup UI.

- Location: `apps/backrest`
- Data: `data/backrest`
- Local backup repository: `backups/restic`
- External encrypted copy: PNY USB drive, `homelab-backups/restic` — incomplete after USB I/O errors ([copy procedure](OPERATIONS.md#usb-backup-copy))
- Access: `http://backrest.home.arpa`
- Recovery verification: [latest report](reports/2026-10-11-backup-recovery.md) and [repeatable test](scripts/verify-backup.py)

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
- Matrix route: `matrix.pentagonlab.org` → `http://127.0.0.1:8008`
- Public HTTP access works through the outbound tunnel behind CGNAT.

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

Lightweight checks run every five minutes through `homelab-monitor.timer`. They check disk space, managed containers, Matrix/Vaultwarden health, and Backrest backup results. Alerts go to the private, unencrypted Matrix room **Server alerts** through `@homelab:pentagonlab.org`, with local journal logging as well. Send `!status` in **Server alerts** for a fresh health report; a separate lightweight timer checks for authorized requests every 15 seconds. Matrix PostgreSQL dumps run hourly and are checked for freshness. See [database backups](OPERATIONS.md#matrix-database-backups) and [monitoring setup](monitoring/README.md).

---

## Messaging

### Matrix Synapse

Matrix homeserver backed by Postgres.

- Location: `apps/matrix`
- Data: `data/matrix`
- Public URL: `https://matrix.pentagonlab.org` through Cloudflare Tunnel
- Server name / user ID domain: `pentagonlab.org`
- Local Synapse port: `127.0.0.1:8008`
- Runtime config: `data/matrix/synapse/homeserver.yaml` (ignored by Git)
- Secrets: `apps/matrix/.env`

Coturn was removed on 2026-10-11 because the home connection is behind CGNAT and has no configured public TURN endpoint. Synapse no longer advertises the Google STUN server or any TURN server. Legacy clients can still message; direct calls may connect, but calls requiring a relay will fail. No MatrixRTC/LiveKit backend is deployed. See [Matrix operations](OPERATIONS.md#matrix) for configuration and checks.

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

Ansible host preparation now covers prerequisite packages, missing directories, and missing shared Docker networks. See [Ansible usage](ansible/README.md). Homepage deployment and HTTPS health verification are available through `ansible/homepage.yml`; other service deployments remain manual.
