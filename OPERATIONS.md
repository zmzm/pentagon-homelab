# 🛠 Operations

Operational commands and troubleshooting guide for the Pentagon homelab.

---

# Docker Basics

## List running containers

docker ps

Show all containers (including stopped):

docker ps -a

---

## View container logs

Show logs:

docker logs CONTAINER_NAME

Follow logs live:

docker logs -f CONTAINER_NAME

Show last 100 lines:

docker logs --tail 100 CONTAINER_NAME

Example:

docker logs -f pihole

---

## Restart container

docker restart CONTAINER_NAME

Example:

docker restart pihole

---

## Stop container

docker stop CONTAINER_NAME

---

## Start container

docker start CONTAINER_NAME

---

# Docker Compose

All application compose files live in:

~/Documents/homelab/apps/

Example:

cd ~/Documents/homelab/apps/pihole

---

## Start services

docker compose up -d

---

## Stop services

docker compose down

---

## Restart services

docker compose restart

---

## Pull latest images

docker compose pull

---

## Recreate containers

docker compose up -d --force-recreate

---

# Secrets

Real environment files are local only and ignored by Git.

Current local secret files:

apps/matrix/.env
apps/netdata/.env
apps/pihole-adapter/.env
apps/portainer/.env

Tracked example files document required variables:

apps/matrix/.env.example
apps/netdata/.env.example
apps/portainer/.env.example

When starting a service, run Docker Compose from that service directory so the local `.env` file is loaded automatically.

Example:

cd ~/Documents/homelab/apps/matrix
docker compose up -d

---

# Netdata

Create the local environment file from the example, then paste the claim values from Netdata Cloud:

cp apps/netdata/.env.example apps/netdata/.env

Start the agent:

cd ~/Documents/homelab/apps/netdata
docker compose up -d

Verify local access:

curl -k https://netdata.home.arpa/api/v3/info

Verify Caddy can reach the container over the `proxy` network:

docker exec caddy wget -S -O - --timeout=5 http://netdata:19999/api/v3/info

Check Cloud claiming logs:

docker logs netdata 2>&1 | grep -i CLAIM

---

# Git

The repository tracks service definitions, static configs, documentation, and incident notes.

Ignored local/runtime paths include:

data/
backups/
apps/*/.env
.agents/
.codex/
cloudflared-linux-arm

Check what would be committed:

git status --short

Check ignored files:

git status --short --ignored

---

# Inspect Docker

## Container details

docker inspect CONTAINER_NAME

---

## Show container resource usage

docker stats

---

## Show container networks

docker network ls

Inspect network:

docker network inspect NETWORK_NAME

---

# Disk Usage

## Docker disk usage

docker system df

---

## Clean unused images

docker image prune

---

## Clean everything unused

docker system prune

---

# Log Investigation

## Show system logs

journalctl -xe

---

## Follow system logs

journalctl -f

---

## Show service logs

journalctl -u SERVICE_NAME

Example:

journalctl -u docker

---

# DNS Troubleshooting

Used during DNS loop incident.

---

## Test DNS resolution

dig google.com

---

## Query specific DNS server

dig google.com @127.0.0.1 -p 5335

---

## Check Pi-hole DNS

dig google.com @PIHOLE_IP

---

## Test domain resolution

dig vault.home.arpa

---

## Trace DNS resolution

dig +trace google.com

---

# Network Diagnostics

## Check open ports

ss -tulnp

---

## Show listening services

netstat -tulnp

---

## Test connection

curl http://vault.home.arpa

---

## Check HTTP headers

curl -I http://vault.home.arpa

---

# File System Navigation

## List files

ls

Detailed list:

ls -lah

---

## Show directory tree

tree

Limit depth:

tree -L 3

---

# File Search

## Find files by name

find . -name "docker-compose.yml"

---

## Find directories

find . -type d -name "data"

---

# Text Search

## Search inside files

grep "vault.home.arpa" -R .

---

## Case insensitive search

grep -i "error" -R .

---

## Search logs for errors

grep -i error logfile.log

---

# Process Monitoring

## Show running processes

ps aux

---

## Filter processes

ps aux | grep docker

---

# System Monitoring

## CPU / Memory

top

Better alternative:

btop

---

## Disk usage

df -h

---

## Directory size

du -sh *

---

# Incident Investigation Workflow

Basic steps when something breaks:

1. Check containers

docker ps

2. Check logs

docker logs CONTAINER_NAME

3. Check DNS

dig google.com

4. Check reverse proxy

curl http://SERVICE_DOMAIN

5. Check ports

ss -tulnp

6. Check system logs

journalctl -xe

---

# Useful Paths

Homelab root:

~/Documents/homelab

Apps:

~/Documents/homelab/apps

Data:

~/Documents/homelab/data

Incidents:

~/Documents/homelab/incidents
