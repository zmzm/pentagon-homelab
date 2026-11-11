# Pentagon Homelab

Raspberry Pi 5 based self-hosted infrastructure managed with Docker Compose.

<img width="1672" height="941" alt="homelab" src="https://github.com/user-attachments/assets/9270ed03-cd07-43aa-a3db-a129b7234910" />

## Documentation

- [Services](SERVICES.md): app inventory, persistent data, ports and secrets.
- [Architecture](ARCHITECTURE.md): routing and component boundaries.
- [Domains](DOMAINS.md): configured names and access paths.
- [Operations](OPERATIONS.md): diagnosis, backups and recovery procedures.
- [Ansible](ansible/README.md): host preparation and core service deployment.
- [Recovery checklist](RECOVERY_CHECKLIST.md): replacement-host prerequisites and acceptance.
- [Engineering instructions](AGENTS.md): repository change and verification rules.

This inventory describes tracked configuration. Deployment reports record observations
at their stated dates; they do not establish current runtime health.

## Hardware

The documented host is a Raspberry Pi 5 with 16 GB RAM running Raspberry Pi OS.
Storage and recovery constraints are recorded in [backup operations](OPERATIONS.md#backup-recovery-verification)
and the [backup recovery report](reports/2026-10-11-backup-recovery.md).

## Applications

| App directory | Purpose |
| --- | --- |
| `apps/backrest` | Restic backup UI and local repository management |
| `apps/caddy` | Reverse proxy and internal TLS |
| `apps/cloudflared` | Outbound Cloudflare Tunnel for public Matrix HTTP access |
| `apps/flowforge` | Planning-only API and read-only inspector around the external runner |
| `apps/hermes` | Personal agent, Matrix conversation, memory, skills and schedules |
| `apps/homepage` | Service dashboard |
| `apps/matrix` | Synapse homeserver and PostgreSQL database |
| `apps/pentagon-gateway` | Tool policy, audit, approvals, Docker broker and Matrix approval relay |
| `apps/pihole` | DNS filtering and local DNS records |
| `apps/pihole-adapter` | Pi-hole summary API for Homepage and SmallTV |
| `apps/portainer` | Docker management UI |
| `apps/smalltv-dashboard` | LAN JSON feeds and notifications for the SmallTV desk display |
| `apps/unbound` | Recursive DNS resolver |
| `apps/vaultwarden` | Bitwarden-compatible password manager |
| `apps/watchtower` | Scheduled image updates for opted-in containers |

The eleven core Compose projects have [Ansible deployment playbooks](ansible/README.md).
Hermes, the gateway, broker, Matrix approval relay and FlowForge services share
[the Hermes Compose project](apps/hermes/docker-compose.yml); follow the
[Hermes operating guide](apps/hermes/README.md) for deployment and tool contracts.
SmallTV has its own [Compose project and device setup](apps/smalltv-dashboard/README.md).
The Interview Assistant Caddy route points to an application managed outside this repository.

## Access and monitoring

Local HTTP services use `home.arpa` names through Pi-hole and Caddy.
Matrix is accessed at `https://matrix.pentagonlab.org` through Cloudflare Tunnel
behind CGNAT. There is no configured TURN relay or MatrixRTC backend;
see [domain routing](DOMAINS.md).

Host systemd jobs provide five-minute health checks, Matrix `!status` responses,
hourly PostgreSQL dumps and weekly isolated recovery verification.
[Monitoring configuration](monitoring/README.md) defines coverage and evidence limits;
the twelve configured container checks exclude the Hermes stack and SmallTV.
Independent external monitoring remains [deferred](monitoring/EXTERNAL_MONITORING.md).
SmallTV consumes an allowlisted summary through a separate thirty-second exporter.

Backrest stores encrypted snapshots locally. The attempted USB copy is incomplete
and unverified after device failures; it is not a recovery source.
See [backup and restore procedures](OPERATIONS.md#backup-recovery-verification).

## Repository and secrets

`apps/` holds service definitions and static configuration; `ansible/` holds
provisioning and deployment automation; `scripts/` and `monitoring/` hold host jobs.
`incidents/` and `reports/` retain incident records and dated verification evidence.

Persistent `data/`, local `backups/`, real `apps/*/.env` files and private Ansible
Vault files are ignored by Git. Tracked `.env.example` files document settings for
Matrix, Portainer, the Pi-hole adapter and Hermes. Restore runtime secrets and data
before deployment; a checkout alone is insufficient for recovery.
