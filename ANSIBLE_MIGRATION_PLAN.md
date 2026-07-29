# Ansible Migration Plan

Plan for moving the homelab toward repeatable Ansible-managed deployment while keeping Docker Compose as the service runtime.

---

# Current State

- Docker Compose is the source of truth for services under `apps/`.
- Persistent runtime data lives under `data/` and is not committed.
- Secrets live in local `.env` files and are not committed.
- Ansible baseline exists under `ansible/`.
- Current Ansible playbook is read-only preflight.

---

# Goal

Use Ansible to make the host reproducible:

- verify host prerequisites
- create required directories
- create Docker networks
- render safe local config files from templates
- deploy Compose apps in a predictable order
- keep secrets out of Git

Docker Compose remains the per-service runtime.

---

# Phase 1: Preflight Baseline

Status: done

Files:

- `ansible/ansible.cfg`
- `ansible/inventory.ini`
- `ansible/group_vars/homelab.yml`
- `ansible/site.yml`

Capabilities:

- local inventory for the `pentagon` host
- shared homelab paths
- Compose app list
- repository path check

Validation:

```bash
cd ~/Documents/homelab/ansible
ansible-playbook site.yml
```

---

# Phase 2: Host Prerequisites

Add a `common` or `docker_host` role that installs and verifies:

- Docker Engine
- Docker Compose plugin
- Git
- curl
- DNS tools
- btop
- restic

Keep this phase idempotent and low-risk. It should not start or stop application containers yet.

Validation:

```bash
docker version
docker compose version
git --version
restic version
```

---

# Phase 3: Directory Layout

Create required base directories with the correct ownership:

- `data/`
- `backups/`
- per-service `data/*` directories

Initial directories to manage:

- `data/caddy`
- `data/cloudflared`
- `data/homepage`
- `data/matrix`
- `data/netdata`
- `data/pihole`
- `data/portainer`
- `data/turn`
- `data/unbound`
- `data/vaultwarden`
- `data/backrest`

Do not change ownership recursively across existing runtime data until each service's ownership requirements are documented.

---

# Phase 4: Docker Networks

Manage shared Docker networks with Ansible.

Initial network:

- `proxy`

Use `community.docker.docker_network` once the collection is installed.

Validation:

```bash
docker network inspect proxy
```

---

# Phase 5: Compose Deployment

Deploy apps with `community.docker.docker_compose_v2`.

Recommended deployment order:

1. `caddy`
2. `unbound`
3. `pihole`
4. `pihole-adapter`
5. `homepage`
6. `portainer`
7. `vaultwarden`
8. `backrest`
9. `matrix`
10. `cloudflared`
11. `turn`
12. `watchtower`
13. `netdata`

Start with one low-risk app first, such as `watchtower` or `homepage`, then expand.

Validation:

```bash
docker ps
docker compose ps
```

---

# Phase 6: Secrets

Move secret rendering into Ansible Vault.

Candidate secrets:

- `MATRIX_POSTGRES_PASSWORD`
- `PORTAINER_HOMEPAGE_WIDGET_KEY`
- `NETDATA_CLAIM_TOKEN`
- `NETDATA_CLAIM_ROOMS`

Keep rendered `.env` files ignored by Git.

Validation:

```bash
git status --short --ignored
```

Confirm `.env` files remain ignored.

---

# Phase 7: Service Health Checks

Add Ansible post-deploy checks for important local routes.

Examples:

```bash
curl -k https://vault.home.arpa
curl -k https://netdata.home.arpa/api/v3/info
curl http://dashboard.home.arpa
dig google.com
```

Prefer checks that match actual user access paths through Caddy and Pi-hole.

---

# Phase 8: Backups and Recovery

Use Ansible to verify backup tooling and expected paths:

- Backrest container exists
- backup repository path exists
- Restic is installed
- latest snapshots can be listed

Do not automate destructive restore workflows until they are tested manually and documented.

---

# Phase 9: Remote Provisioning

After local Ansible is stable, add a separate SSH inventory for provisioning a new host.

Do not replace the current local inventory. Keep both:

- local inventory for operations on the current host
- SSH inventory for bootstrap or rebuild scenarios

Remote inventory should avoid committing private IPs or usernames if the repo is public.

---

# Guardrails

- Do not commit real `.env` files.
- Do not commit `data/` or `backups/`.
- Do not template service configs until the current static config is understood.
- Do not automate destructive restore or cleanup commands early.
- Prefer one small role or one service migration per commit.
- Validate each phase with a command that can be rerun safely.

---

# Next Commit Candidates

1. Add Ansible role skeletons.
2. Add Docker network management for `proxy`.
3. Add directory creation tasks for empty base paths.
4. Add Compose deployment for one low-risk service.
5. Add Ansible Vault templates for one `.env` file.
