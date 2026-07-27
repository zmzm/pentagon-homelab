# 🌐 Domains

Domain routing configuration for the Pentagon homelab.

All domains are served through the Caddy reverse proxy.

---

# Local Domain

Primary internal domain:

home.arpa

This domain is resolved locally through Pi-hole.

---

# Service Domains

| Domain | Service | Container | Notes |
|------|------|------|------|
| vault.home.arpa | Vaultwarden | vaultwarden | Password manager |
| dash.home.arpa | Homarr | homarr | Main dashboard |
| docker.home.arpa | Portainer | portainer | Docker management |
| pihole.home.arpa | Pi-hole | pihole | DNS admin panel |
| interview-assistant.home.arpa | Interview Assistant | nextapp | Next.js application |

---

# Reverse Proxy

All services are routed through Caddy.

Caddy configuration location:

apps/caddy/Caddyfile

Example routing:

vault.home.arpa → vaultwarden:80  
dash.home.arpa → homarr:7575  
docker.home.arpa → portainer:9000  
pihole.home.arpa → host:8081  
interview-assistant.home.arpa → nextapp:3000  

---

# Direct Access Services

Some services are currently accessed directly via ports.

| Service | Port |
|------|------|
| Homepage | 3002 |

Example:

http://SERVER_IP:3002

---

# DNS Flow

Client devices use Pi-hole as DNS resolver.

DNS flow:

Client
  ↓
Pi-hole
  ↓
Unbound
  ↓
Internet root DNS servers

---

# Future Domains

Potential future services may include:

ai.home.arpa  
monitor.home.arpa  
logs.home.arpa  
git.home.arpa  

---

# Notes

- All service routing is handled by Caddy.
- Internal TLS is supported by Caddy.
- Pi-hole manages local DNS records.
- Unbound provides recursive DNS resolution.
