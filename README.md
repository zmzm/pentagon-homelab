# 🏠 Pentagon Homelab

Raspberry Pi 5 based self-hosted infrastructure.

## Hardware

- Device: Raspberry Pi 5
- RAM: 16 GB
- OS: Raspberry Pi OS
- Storage:
  - NVMe (temporary)
  - SSD planned

---

# 📁 Repository Structure

homelab/
├── apps/        # docker compose files and app configs  
├── data/        # persistent service data  
└── incidents/   # incident reports and troubleshooting notes  

Apps directory contains application configuration and docker-compose files.

apps/
├── caddy  
├── homarr  
├── homepage  
├── pihole  
├── portainer  
├── unbound  
└── vaultwarden  

Data directory contains persistent volumes mounted into containers.

data/
├── caddy  
├── homarr  
├── homepage  
├── pihole  
├── portainer  
├── unbound  
└── vaultwarden  

---

# 🐳 Services

## Reverse Proxy

### Caddy

Handles routing for internal services.

Location:  
apps/caddy

Data:  
data/caddy

Responsibilities:

- Reverse proxy
- Internal TLS
- Domain routing

Domains:

- vault.home.arpa
- dash.home.arpa
- docker.home.arpa
- pihole.home.arpa
- interview-assistant.home.arpa

---

## Password Manager

### Vaultwarden

Bitwarden-compatible password manager.

Location:  
apps/vaultwarden

Data:  
data/vaultwarden

Access:  
https://vault.home.arpa

---

## DNS & Network

### Pi-hole

Network-wide ad blocker and DNS manager.

Location:  
apps/pihole

Data:  
data/pihole

Access:  
http://pihole.home.arpa

Uses Unbound as upstream DNS resolver.

---

### Unbound

Recursive DNS resolver.

Location:  
apps/unbound

Data:  
data/unbound

Port:  
127.0.0.1:5335

Used by Pi-hole.

---

## Docker Management

### Portainer

Docker management UI.

Location:  
apps/portainer

Data:  
data/portainer

Access:  
http://docker.home.arpa

---

## Dashboards

### Homarr

Main service dashboard.

Location:  
apps/homarr

Data:  
data/homarr

Access:  
http://dash.home.arpa

---

### Homepage

Secondary dashboard (experimentation / widgets).

Location:  
apps/homepage

Data:  
data/homepage

Direct access:  
http://SERVER_IP:3002

---

## Applications

### Interview Assistant (Next.js)

Next.js application running in Docker.

Container name:  
nextapp

Access:  
http://interview-assistant.home.arpa

---

# 🌐 Domain Routing

Managed via Caddy.

vault.home.arpa → vaultwarden  
dash.home.arpa → homarr  
docker.home.arpa → portainer  
pihole.home.arpa → pihole  
interview-assistant.home.arpa → nextapp  

---

# 🧠 Notes

- Docker Compose used for service management.
- Application configs stored in apps/.
- Persistent data stored in data/.
- Caddy handles internal TLS and routing.
- Pi-hole + Unbound used for DNS resolution.

---

# 🛠 Future Improvements

Possible additions:

- Centralized logging
- Automated container updates
- Monitoring stack
- Backup strategy
- AI assistant services

---

# 📋 Incidents

Operational issues and resolutions are documented in:

incidents/

This directory contains postmortems and troubleshooting notes.
