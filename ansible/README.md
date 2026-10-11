# Ansible host preparation

`site.yml` remains the read-only preflight. `prepare.yml` runs that preflight, then installs missing prerequisites, ensures Docker is running/enabled, creates missing base directories, and creates missing shared Docker networks. It does not deploy Compose applications or render secrets.

Run commands from this directory so Ansible loads `ansible.cfg` and the local inventory:

```bash
cd ~/Documents/homelab/ansible
ansible-playbook site.yml
ansible-playbook prepare.yml --syntax-check
ansible-playbook prepare.yml --check --diff
ansible-playbook prepare.yml
# Repeat: an already prepared host should report changed=0.
ansible-playbook prepare.yml
```

Preparation uses privilege escalation (`become: true`). Add `-K` if sudo requires a password. The current inventory targets only the local `pentagon` host.

The host needs Python 3, Ansible, and the `community.docker` collection. The tested baseline is Ansible core 2.19.4 and community.docker 4.7.0. For a controller without that collection:

```bash
ansible-galaxy collection install -r requirements.yml
```

The prerequisite role assumes Debian and an already configured official Docker apt repository. It installs missing packages with `state: present`; it does not upgrade installed packages, refresh apt metadata, configure Docker's repository, replace another Docker distribution, or change Docker daemon settings. On a fresh host, configure Docker's apt repository and refresh package metadata before running it. This is preparation for the current host, not yet a complete bare-metal bootstrap.

`group_vars/homelab.yml` declares package names, paths, the account used for new directories, and shared networks. Change those values before using another account or repository location. The repository and owning account must already exist.

Existing data directory ownership and modes are preserved. Missing directories are created with declared ownership and modes; no recursive changes are made. Existing files/symlinks in directory paths fail validation. Service-specific subdirectories and UID/GID requirements still need documenting before full deployment. Retired TURN and Netdata paths are absent.

Existing shared networks are inspected and must use the bridge driver. They are left intact, including subnet, labels, options, and container connections. Only missing networks are created. Network recreation and IPAM changes require a separate reviewed change.

You can target individual roles after the preflight:

```bash
ansible-playbook prepare.yml --tags directories --check --diff
ansible-playbook prepare.yml --tags networks --check --diff
```

The preflight is tagged `always` so these commands still validate the repository. Tool verification commands run in check mode because they are read-only. Preview mode cannot simulate installing an absent Docker daemon and then querying it; bootstrap in stages on a new host.

Homepage is the first automated Compose deployment; see below. Other applications, secret rendering, monitoring-unit deployment, backups-unit deployment, and remote provisioning remain separate work.

Validation on 2026-10-11: syntax validation passed; the production preview and two live runs reported `changed=0`, `failed=0`. An isolated temporary directory and unused bridge network were predicted and created (`changed=2`), then a repeat reported `changed=0`. The new directory was verified root-owned with mode 0700. Both temporary resources were removed. Production monitoring remained healthy across all 17 checks.

## Homepage deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook homepage.yml --syntax-check
ansible-playbook homepage.yml --check --diff
ansible-playbook homepage.yml
```

`homepage.yml` runs the read-only preflight, verifies required runtime config files and the external `proxy` network, validates Compose without printing expanded configuration, and deploys only the existing `homepage` project through `community.docker.docker_compose_v2`. It waits up to 120 seconds for the container's health check, then requests `https://dashboard.home.arpa` through host DNS and Caddy with certificate verification using Caddy's local CA. Preview mode skips that post-deployment HTTP check.

Compose remains the service definition at `apps/homepage/docker-compose.yml`. Deployment uses `pull: missing`, `build: never`, and `recreate: auto`: an installed image is reused; a missing image may be downloaded; configuration or local-image changes can recreate Homepage. It does not remove orphan containers or run another Compose project. Watchtower remains enabled under the existing definition and can update the image independently.

Restore `data/homepage/config` from backup before rebuilding. The role requires `settings.yaml`, `services.yaml`, `widgets.yaml`, and `docker.yaml`; it preserves their contents, ownership, and modes. Other configuration and customizations remain in the same directory. Current top-level config files belong to `pentagon-admin:pentagon-admin` (0644 or 0664), and the config directory is 0755. The current image runs as root, which can read those files and the mounted Docker socket. This role does not render widget credentials, change runtime ownership, or generate a replacement dashboard.

Caddy, its restored local CA, local DNS for `dashboard.home.arpa`, and the `proxy` network must already work. Prepare a new host with `prepare.yml` and restore runtime config first. Compose bind paths are currently absolute; update them together with inventory variables when moving the repository. URL and CA path are configurable with `homelab_homepage_url` and `homelab_homepage_ca_path`.

References: [Compose deployment module](https://docs.ansible.com/projects/ansible/latest/collections/community/docker/docker_compose_v2_module.html).

Homepage validation on 2026-10-11: syntax and preview passed; the first deployment reconciled the existing container (`changed=1`), and the repeat completed with `changed=0`, `failed=0`. Both live runs passed the HTTPS route check. Existing top-level runtime config contents, owners, groups, and modes were unchanged. The deployed image was the same local image used before deployment.
