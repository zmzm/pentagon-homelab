# 🌐 Domains

Domain routing configuration for the Pentagon homelab.

Most service domains are served through the Caddy reverse proxy. Local names use `home.arpa` and are resolved through Pi-hole.

---

# Service Domains

| Domain | Service | Target | Notes |
|------|------|------|------|
| `matrix.pentagonlab.org` | Matrix Synapse | Cloudflare Tunnel → `http://127.0.0.1:8008` | Public HTTPS; separate from Caddy |
| `vault.home.arpa` | Vaultwarden | `vaultwarden:80` | Password manager, Caddy internal TLS enabled |
| `docker.home.arpa` | Portainer | `portainer:9000` | Docker management |
| `pihole.home.arpa` | Pi-hole | `100.126.16.76:8081` | DNS admin panel |
| `dashboard.home.arpa` | Homepage | `homepage:3000` | Main dashboard |
| `backrest.home.arpa` | Backrest | `backrest:9898` | Restic backup UI, Caddy internal TLS enabled |
| `interview-assistant.home.arpa` | Interview Assistant | `nextapp:4000` | Route exists in Caddyfile; no local app compose project is tracked |

---

# Reverse Proxy

Caddy configuration location:

```text
apps/caddy/Caddyfile
```

Current Caddy routes:

```text
vault.home.arpa                → vaultwarden:80
docker.home.arpa               → portainer:9000
pihole.home.arpa               → 100.126.16.76:8081
interview-assistant.home.arpa  → nextapp:4000
dashboard.home.arpa            → homepage:3000
backrest.home.arpa             → backrest:9898
```

---

# Matrix Domain and Calling

`pentagonlab.org` is the Matrix server name used in user IDs. Clients access the homeserver at `https://matrix.pentagonlab.org/` through Cloudflare Tunnel.

The home connection is behind CGNAT. Cloudflare's public addresses for `matrix.pentagonlab.org` are proxy addresses, not a directly reachable public IP for the Pi.

There is no configured TURN hostname: `turn.pentagonlab.org` did not resolve during the 2026-10-11 check. Coturn was removed, and Synapse advertises no STUN/TURN endpoints. A future TURN service would need a reachable public endpoint, such as an ISP-provided public IP or a VPS, and could use a DNS-only subdomain of `pentagonlab.org`.

---

# Direct / Local Access

Some services also expose host-local ports:

| Service | Port | Notes |
|------|------|------|
| Pi-hole | `8081` | Host network mode |
| Unbound | `127.0.0.1:5335` | Recursive DNS |
| Matrix Synapse | `127.0.0.1:8008` | Local homeserver listener |

---

# DNS Flow

```text
Client
  ↓
Pi-hole
  ↓
Unbound
  ↓
Internet root DNS servers
```

---

# Future Domains

Potential future services may include:

```text
ai.home.arpa
logs.home.arpa
git.home.arpa
```

---

# Notes

- Caddy handles reverse proxy routing.
- Pi-hole manages local DNS records.
- Unbound provides recursive DNS resolution.
- Cloudflared is configured separately through `data/cloudflared`, which is not committed.
