# 🏗 Homelab Architecture

Infrastructure overview for the Pentagon homelab.

---

# High Level Architecture

Clients access services through Caddy reverse proxy.

Clients (Browsers / Devices)
        │
        ▼
      Caddy
        │
 ┌──────┼───────────────┬───────────────┬───────────────┐
 │      │               │               │
 ▼      ▼               ▼               ▼
Vaultwarden        Homarr          Portainer        Next.js App
(passwords)        (dashboard)     (docker UI)      (interview assistant)

Homepage dashboard is currently accessed directly via port 3002.

---

# DNS Architecture

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

Pi-hole handles DNS filtering and local domain resolution.
Unbound acts as a recursive resolver.

---

# Service Layout

homelab/

apps/
├── caddy
├── homarr
├── homepage
├── pihole
├── portainer
├── unbound
└── vaultwarden

data/
├── caddy
├── homarr
├── homepage
├── pihole
├── portainer
├── unbound
└── vaultwarden

incidents/

apps/ contains docker-compose files and configuration.

data/ contains persistent service data mounted into containers.

incidents/ contains postmortems and troubleshooting notes.

---

# Reverse Proxy Routing

vault.home.arpa                → vaultwarden
dash.home.arpa                 → homarr
docker.home.arpa               → portainer
pihole.home.arpa               → pihole
interview-assistant.home.arpa  → nextapp

---

# Container Overview

caddy        → reverse proxy
vaultwarden  → password manager
pihole       → DNS + ad blocking
unbound      → recursive DNS resolver
portainer    → docker management UI
homarr       → main dashboard
homepage     → experimental dashboard
nextapp      → interview assistant application

---

# Security Notes

- Internal TLS handled by Caddy.
- Vaultwarden only exposed through reverse proxy.
- DNS queries filtered by Pi-hole.
- Unbound used as recursive resolver instead of public DNS providers.
- Docker containers isolated via docker networking.

---

# Future Architecture

Potential additions to the infrastructure:

- Monitoring stack (Grafana / Prometheus)
- Centralized logging
- Automated container updates
- Backup automation
- AI assistant services
