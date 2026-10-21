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

For a future replacement machine, use the separate [SSH inventory and remote preparation guide](REMOTE_PROVISIONING.md). `inventory.ssh.example.yml` is a placeholder template; the private `inventory.ssh.yml` is ignored by Git. `remote-preflight.yml` verifies an explicit target without provisioning it. The shared preflight automatically verifies identity for hosts in `homelab_replacement` before the existing playbooks proceed; local inventory behavior is preserved.

The host needs Python 3, Ansible, and the `community.docker` collection. The tested baseline is Ansible core 2.19.4 and community.docker 4.7.0. For a controller without that collection:

```bash
ansible-galaxy collection install -r requirements.yml
```

The prerequisite role configures a missing official Docker apt repository on Debian 12/13 and Ubuntu 22.04/24.04/26.04 LTS, for ARM64/AMD64. It preserves a matching existing legacy `.list` or Deb822 `.sources` entry and its signing-key file. Duplicate, mismatched, disabled/conflicting destination or signature-bypassing entries stop preparation; unsupported distributions/architectures require separate review. Existing distribution Docker/runtime packages and unmanaged Docker binaries are rejected rather than removed automatically.

Validation on 2026-10-21: production preview, deployment, repeat and final preview passed with `changed=0`, `failed=0`. Existing Docker package versions, daemon PID, managed container IDs and repository/key files were preserved. Temporary Debian ARM64 and Ubuntu AMD64 apt roots verified repository creation, key fingerprint checks, signed metadata and package candidates; no packages were installed in these fixtures. All 15 regression tests and all 18 production health checks passed. A full fresh-host installation remains untested. See [the bootstrap report](../reports/2026-10-21-docker-bootstrap.md).

Missing HTTPS/GPG tools are installed first. A new Docker key is downloaded over verified HTTPS, checked against the expected primary fingerprint, and referenced by a dedicated `Signed-By` source. Repository metadata is refreshed when adding a source or installing missing prerequisites. Existing requested package versions are pinned for that run, including Docker Engine/CLI, containerd and Buildx/Compose plugins; missing packages use the current stable candidate. This is not a permanent cross-host version lock. Docker is ensured running/enabled without changing daemon settings. No convenience installation script is used. This automates package/repository preparation, not OS installation or a complete bare-metal rebuild. Sources: [Docker Debian installation](https://docs.docker.com/engine/install/debian/) and [Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/).

`group_vars/homelab.yml` declares package names, paths, the account used for new directories, and shared networks. Change those values before using another account or repository location. The repository and owning account must already exist.

Existing data directory ownership and modes are preserved. Missing directories are created with declared ownership and modes; no recursive changes are made. Existing files/symlinks in directory paths fail validation. Service-specific subdirectories and UID/GID requirements still need documenting before full deployment. Retired TURN and Netdata paths are absent.

Existing shared networks are inspected and must use the bridge driver. They are left intact, including subnet, labels, options, and container connections. Only missing networks are created. Network recreation and IPAM changes require a separate reviewed change.

You can target individual roles after the preflight:

```bash
ansible-playbook prepare.yml --tags directories --check --diff
ansible-playbook prepare.yml --tags networks --check --diff
```

The preflight is tagged `always` so these commands still validate the repository. Tool verification commands run in check mode because they are read-only. For a missing repository, preview reports the planned setup without downloading keys or updating apt metadata. Package installation/daemon checks that require Docker are deferred when it is absent; a preview is not proof of installable packages on a fresh host. Bootstrap with `--tags prerequisites`, then preview directories/networks separately, as described in [remote preparation](REMOTE_PROVISIONING.md).

All eleven Compose projects have dedicated deployment playbooks: Caddy, Pi-hole, Homepage, Portainer, Watchtower, Vaultwarden, Backrest, Unbound, Matrix, the Pi-hole adapter, and Cloudflare Tunnel. Portainer also supports rendering its environment file from Vault variables. Monitoring and Matrix database backup units are managed by `scheduled-jobs.yml`. Full rebuild testing, further Vault rendering, and remote provisioning remain separate work.

Validation on 2026-10-11: syntax validation passed; the production preview and two live runs reported `changed=0`, `failed=0`. An isolated temporary directory and unused bridge network were predicted and created (`changed=2`), then a repeat reported `changed=0`. The new directory was verified root-owned with mode 0700. Both temporary resources were removed. Production monitoring remained healthy across all 17 checks.

## Caddy deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook caddy.yml --syntax-check
ansible-playbook caddy.yml --check --diff
ansible-playbook caddy.yml
```

Run `prepare.yml` and restore the complete `data/caddy/data` and `data/caddy/config` directories first. The role requires the existing local CA's `root.crt`, `root.key`, `intermediate.crt`, and `intermediate.key`; missing files stop deployment. The directories' current ownership is `pentagon-admin:pentagon-admin`, mode 0775. Root CA files are owned by the same account, mode 0600; intermediate files are root-owned, mode 0600. The role preserves these contents, owners and modes. The current Caddy image runs as root. CA keys remain restored runtime secrets; they are not generated or templated by this role.

Compose now treats `proxy` as an external network, matching the existing Ansible network-preparation role. Caddy requires that bridge network to exist and does not recreate it. The role verifies all three bind mounts against inventory, including the read-only Caddyfile, then validates configuration in a disposable container using read-only `/data` and `/config` mounts and no published ports. Installed images are reused; a missing `caddy:2` image is downloaded during a live run. Preview runs disposable validation when the image is already installed and otherwise defers validation until the live run.

Deployment uses `pull: missing`, `build: never`, `recreate: auto`, and no orphan removal. A stale Caddyfile bind (possible after an atomic host-file replacement) is detected by comparing the mounted checksum with the checked host file and forces container recreation to refresh that mount. After deployment, the role compares adapted Caddyfile JSON with the running configuration through the container-local admin API. If they differ, it uses `caddy reload` for a graceful update. This relies on the image's `wget` and `sha256sum` utilities and Caddy's default localhost admin API. The admin API is not published to the host. Preview does not perform the active-configuration comparison/reload.

Six route checks use host DNS and trusted TLS: Vaultwarden health, Portainer API, Pi-hole admin, Homepage, Backrest, and the interview assistant. Login redirects are followed with certificate validation. All upstreams must be running, including `nextapp`, whose application project is outside this repository. Override `homelab_caddy_route_checks` for a different intended set. For a replacement-host bootstrap before upstreams are started, use `-e homelab_caddy_check_routes=false`, then rerun with the default checks after deploying upstreams. Core recovery, mount and configuration validation still runs. These checks do not exercise user authentication or public Matrix access.

Configuration remains at `apps/caddy/Caddyfile`; edit it and rerun the playbook. Update absolute Compose data paths together with inventory when moving the checkout. See [Caddy command-line validation and reload](https://caddyserver.com/docs/command-line).

Validation on 2026-10-19: syntax, preview, deployment, and repeat passed with `changed=0`, `failed=0`. Both live runs verified all six HTTPS routes (`ok=22`). Image, ports, environment, mounts, shared network ID, Caddyfile, and all four CA certificate/key contents, ownership and modes were verified unchanged. Missing CA-key and invalid-Caddyfile fixtures stopped before deployment. A separate container with no network or published ports verified configuration comparison, graceful reload, unchanged comparison, stale-file-bind detection, and bind refresh after recreation, using no production CA data. All 17 production health checks passed afterwards. A full replacement-host rebuild and CA renewal were not exercised.

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

## Portainer deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook portainer.yml --syntax-check
ansible-playbook portainer.yml --check --diff
ansible-playbook portainer.yml
```

The role requires the restored `data/portainer/data/portainer.db`, the existing `proxy` network, and Caddy's local CA. It preserves the database and existing directory ownership. The current data directory is owned by `pentagon-admin:pentagon-admin` with mode 0755; `portainer.db` is 0600. The current Portainer image runs as root (empty Docker user setting) and mounts the Docker socket. Restore the complete Portainer data directory before rebuilding; the database check prevents accidentally initializing a new instance.

Deployment reuses `apps/portainer/docker-compose.yml` with `pull: missing`, `build: never`, `recreate: auto`, and no orphan removal. An existing image is reused; a missing image can be downloaded. Configuration or image changes can recreate the container. Watchtower remains enabled in the Compose definition. After deployment, the role verifies `https://docker.home.arpa/api/status` through DNS and Caddy using the local CA and requires an API version in the response. This checks API reachability, not administrator authentication or widget authorization. Configure the route with `homelab_portainer_url` and `homelab_portainer_ca_path`.

Without Vault variables, the existing `.env` content is preserved and its permissions are restricted to 0600. Compose validation and deployment output are hidden because container labels include the Homepage API key.

Validation on 2026-10-19: syntax and production preview passed; deployment reconciled Portainer and restricted `.env` permissions (`changed=2`), and a repeat passed with `changed=0`, `failed=0`. Both deployments passed the HTTPS API check. Existing `.env` contents were verified unchanged, and the existing local image was reused.

## Portainer secret recovery with Ansible Vault

Recommended: store a separate Vault password in your password manager and supply it interactively. Vault encrypts the saved service key; the running application still needs a plaintext `.env`, restricted to mode 0600. Keep the Vault password outside this server and available during disaster recovery.

Create the encrypted variables file from the existing working key:

```bash
cd ~/Documents/homelab/ansible
python3 import-portainer-vault.py
```

The helper prompts for a new Vault password, reads the existing key without printing it, and creates `vars/portainer.vault.yml` with mode 0600. It writes no additional plaintext copy, refuses to overwrite an existing destination, and leaves the source `.env` unchanged. It rejects empty keys, unsupported characters, and additional environment assignments. `--vault-password-file /path/to/file` is available if an external password file is already managed. Never put a real password or API key in a command-line argument or chat.

Use the encrypted variables for rendering and deployment:

```bash
ansible-playbook portainer.yml -e @vars/portainer.vault.yml --ask-vault-pass --check --diff
ansible-playbook portainer.yml -e @vars/portainer.vault.yml --ask-vault-pass
```

The variables file supplies `vault_portainer_homepage_widget_key`; the role renders only `PORTAINER_HOMEPAGE_WIDGET_KEY` using the existing key, with secret output and template diffs suppressed. During preview the template is not written, so Compose uses the currently installed `.env`. If `.env` is missing, preview skips Compose validation/deployment; a live run renders it before running Compose. Do not use the example placeholder as a real credential.

Both `.env` and `vars/*.vault.yml` are ignored by Git. Save the encrypted variables file with your recovery material as well as keeping its unlock password in your password manager. The existing runtime secret remains in the configured backups; adding Vault here does not replicate backups outside the server. The user initialized the production variables file locally on 2026-10-19. Its encrypted header, mode 0600, and Git exclusion are verified; the user-provided production run confirms successful decryption and deployment (`ok=15`, `changed=1`, `failed=0`, `unreachable=0`). Only environment rendering changed; Compose deployment and the HTTPS API check reported `ok`. On 2026-10-21 the local finish helper verified two production-Vault runs, both `ok=15`, `changed=0`, `unreachable=0`, `failed=0`, including the HTTPS API check.

Validation on 2026-10-19 used a disposable fixture key and password: encrypted import and template rendering passed, encrypted files and rendered `.env` were 0600, an existing Vault could not be overwritten, empty keys were rejected, and `--diff` output contained no fixture key. Temporary validation files were removed.

References: [Ansible Vault](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault.html), [Compose deployment module](https://docs.ansible.com/projects/ansible/latest/collections/community/docker/docker_compose_v2_module.html).

## Watchtower deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook watchtower.yml --syntax-check
ansible-playbook watchtower.yml --check --diff
ansible-playbook watchtower.yml
```

The role requires the versioned `apps/watchtower/docker-compose.yml`, a running Docker daemon with its socket at `/var/run/docker.sock`, and the existing `proxy` network. It validates Compose, deploys only the `watchtower` project, waits for Docker health, and explicitly runs the image's `/watchtower --health-check` command. Preview skips the explicit health command. Watchtower has no application data directory, local environment file, or service secret to restore; its configuration is in Compose. Host preparation and access to the container registry are needed on a replacement host without the image.

Deployment uses `pull: missing`, `build: never`, `recreate: auto`, and no orphan removal. It reuses an existing image; a missing image may be downloaded, and configuration/local-image changes can recreate Watchtower. The Compose command remains `--cleanup --label-enable --schedule "0 0 4 * * *"`; scheduling follows the container's timezone. `DOCKER_API_VERSION=1.44`, the restart policy, and the existing socket mount are preserved. The role invokes Watchtower's health-check mode; automatic container updates continue under its existing schedule and label selection.

The image currently runs as root (empty Docker user setting). The Docker socket is `root:docker`, mode 0660; this role checks that it is a socket and does not change its ownership or permissions. There is no public Watchtower HTTP route; its built-in container health check is used for post-deployment verification.

Validation on 2026-10-19: syntax, production preview, deployment, and repeat passed. Preview reported `changed=0`; both live runs reported `ok=13`, `changed=0`, `failed=0`, including the explicit built-in health check. The existing image, command/schedule, environment, socket mount, restart policy, and Compose file contents were verified unchanged. All 17 production health checks passed afterwards. This validates deployment against the current host; a replacement-host rebuild and an actual automatic image update were not exercised.

## Vaultwarden deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook vaultwarden.yml --syntax-check
ansible-playbook vaultwarden.yml --check --diff
ansible-playbook vaultwarden.yml
```

Restore the complete `data/vaultwarden/data` directory before deployment, along with Caddy's local CA. The role requires a real directory and nonempty, regular `db.sqlite3` and `rsa_key.pem` files. It checks SQLite through a read-only connection using `PRAGMA quick_check` and requires the Vaultwarden `users` table without reading user records. This prevents a missing, corrupt, or unrelated database from silently becoming a new instance. It does not prove the presence of every expected account, vault entry, or attachment.

Restore any attachments, Send files, and admin configuration that existed in the backup. SQLite restoration must match the backup method: a raw database/WAL copy requires the matching pair; a SQLite backup requires avoiding a stale WAL from another database. Stop Vaultwarden before restoring its data and follow the [upstream recovery instructions](https://github.com/dani-garcia/vaultwarden/wiki/Backing-up-your-vault#restoring-backup-data). This deployment role does not restore, remove, or replace database files, signing keys, or WAL files.

The role requires the existing `proxy` network and validates the Compose definition, including that `/data` is a writable bind mount of exactly the directory checked above. The current Compose bind path is absolute; inventory changes must be accompanied by a matching Compose change. It deploys only the `vaultwarden` project with `pull: missing`, `build: never`, `recreate: auto`, and no orphan removal. An existing image is reused; a missing image can be downloaded, and configuration/local-image changes can recreate the container. The source Compose file retains `SIGNUPS_ALLOWED: false` and `DOMAIN: https://vault.home.arpa`.

The current image runs as root (empty Docker user setting). The data directory is owned by `pentagon-admin:pentagon-admin` with mode 0755; the database and signing key are owned by the same account with mode 0644. The role preserves existing ownership, modes, and application configuration. There is currently no service `.env` to render; the signing key remains in restored runtime data and is not copied into Git or Ansible Vault.

Deployment waits for Docker health, then checks both `/alive` and the web vault `/` through host DNS and Caddy, with Caddy's CA and certificate verification. Preview performs database/mount validation but skips HTTPS checks. Configure the checked URL and CA path with `homelab_vaultwarden_url` and `homelab_vaultwarden_ca_path`; changing the URL does not edit Compose's `DOMAIN` or Caddy. These checks establish service reachability, not a user login, vault decryption, or a complete recovery exercise.

Validation on 2026-10-19: syntax, production preview, deployment, and repeat passed (`changed=0`, `failed=0`). Both live runs passed the SQLite check and both HTTPS endpoints (`ok=15`). The running image, environment, data mount, restart policy, signing-key contents, existing data-directory/database/key ownership and modes, and Compose file were verified unchanged. Disposable fixtures confirmed that a missing database, an invalid database, and a mismatch between checked data and the Compose mount all stop before deployment. All 17 production health checks passed afterwards.

## Backrest deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook backrest.yml --syntax-check
ansible-playbook backrest.yml --check --diff
ansible-playbook backrest.yml
```

Restore the complete Backrest configuration and data directories, the local Restic repository, and Caddy's CA first. The role requires `config/config.json`, `data/kvdb.sqlite`, `data/oplog.sqlite`, and `backups/restic/config`. It supports the current single repository at `/repos/restic` and the plan identified by `homelab_backrest_plan` (default `pentagon-backup`). It verifies the saved repository password by opening the encrypted repository configuration with `restic --no-cache --no-lock cat config`; the password is passed through the subprocess environment and all credential-related task output is hidden. This reads configuration without initializing, backing up, restoring, pruning, or checking the whole repository.

All six Compose mounts are verified against inventory, including the read-only source checkout. Existing runtime ownership and permissions are preserved; only missing cache/temporary directories are created as the homelab account with mode 0700. Current config is root-owned 0600, state databases belong to the homelab account with mode 0644, and existing Backrest directories are 0775. Restore the complete data directory, including its signing secret and database/WAL files, to retain history and sessions. The current image runs as root.

Before reconciling a running Backrest, the role waits up to about a minute for operations reported as `STATUS_INPROGRESS` to finish. Future scheduled operations do not block deployment. It then deploys only Backrest with `pull: missing`, `build: never`, and `recreate: auto`, and checks the HTTPS UI and saved plan history through the API. Authentication is currently disabled in Backrest; enabling it requires adding authenticated API verification. URL and CA are configurable with `homelab_backrest_url` and `homelab_backrest_ca_path`. See [Backrest configuration recovery guidance](https://garethgeorge.github.io/backrest/introduction/getting-started).

## Unbound deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook unbound.yml --syntax-check
ansible-playbook unbound.yml --check --diff
ansible-playbook unbound.yml
```

Unbound has no persistent application data or secret to restore; its configuration is the versioned `apps/unbound/unbound.conf`. The role verifies the Compose config mount, obtains the image only if missing, and validates syntax with `unbound-checkconf` in a disposable container before deployment. The validation container uses the configuration read-only, publishes no DNS ports, and is removed afterwards. Preview also performs this validation when the image is installed; on a new host it predicts the image download and defers syntax validation to a live run. Compose may create its project network for the validation container.

The role uses the existing Compose definition with `pull: missing`, `build: never`, and `recreate: auto`. It preserves the loopback-only `127.0.0.1:5335` UDP/TCP bindings and configuration ownership/permissions. It then queries `homelab_unbound_test_name` (default `example.com`) directly over UDP and TCP, requiring `NOERROR` and an IPv4 answer. These checks require working internet access; they do not verify the complete Pi-hole DNS path or every DNSSEC failure case. No shared `proxy` network is needed. The image currently runs as root. Reference: [unbound-checkconf](https://nlnetlabs.nl/documentation/unbound/unbound-checkconf/).

## Pi-hole deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook pihole.yml --syntax-check
ansible-playbook pihole.yml --check --diff
ansible-playbook pihole.yml
```

Restore both `data/pihole/etc-pihole` and `data/pihole/etc-dnsmasq.d`, including the complete configuration/databases, and Caddy's local CA. Start Unbound first and have Caddy available for the final web check. The role requires nonempty `pihole.toml`, `gravity.db`, `pihole-FTL.db`, and generated `dnsmasq.conf`; it does not initialize replacement data. The target's system Python needs `tomllib` (Python 3.11 or newer).

Preflight parses the restored TOML privately, requires the saved API password hash, verifies the expected Unbound upstream and DNS port, and rejects enabled conditional forwarding because of the previous [DNS loop incident](../incidents/2026-03-08-dns-loop.md). It also requires configured IPv4 records for the six local service names in `homelab_pihole_local_names`. Only those records are exported for verification; credentials are not printed. `gravity.db` is checked through a read-only SQLite connection using `PRAGMA quick_check` and required table names. The larger query-history database is checked for presence, not scanned or exposed.

The role verifies host networking and both writable data mounts against inventory. It rejects Compose environment overrides for the restored DNS upstreams, local records, conditional forwarding, DNS port, or password; review the role when intentionally moving those settings into environment variables. Pi-hole makes environment-managed settings read-only in the UI, so this role keeps the current runtime configuration authoritative. See [Pi-hole configuration precedence](https://docs.pi-hole.net/docker/configuration/).

Unbound must answer over UDP and TCP at `127.0.0.1:5335` before deployment. A disposable container runs `pihole-FTL dnsmasq-test` with networking disabled, no published ports, and both restored directories mounted read-only. Preview performs native validation when the image is installed; if missing, preview predicts the image download and defers that validation to the live run. Deployment uses the existing Compose definition with `pull: missing`, `build: never`, `recreate: auto`, no orphan removal, and a wait for Docker health. It preserves host networking, 128 MiB shared memory, configured web port 8081, timezone, and existing runtime settings. The current image runs as root; this role adds no Docker capabilities or new host services.

After deployment, public IPv4 resolution is checked through Pi-hole at `127.0.0.1:53` over UDP and TCP. Each required local name is checked over both protocols against its restored IPv4 record. The admin page is then checked through host DNS and Caddy with trusted TLS, following the normal login redirect. Defaults are `homelab_pihole_url: https://pihole.home.arpa`, `homelab_pihole_ca_path: "{{ homelab_homepage_ca_path }}"`, and public query name `example.com`. The current upstream layout is specifically Unbound on loopback port 5335; changing it requires reviewing both validation and DNS checks.

No configuration, password, blocklist, DNS record, ownership or permission is rendered/changed by the role. Existing `etc-pihole` is owned by the homelab account with mode 0775, `etc-dnsmasq.d` is 0755, `pihole.toml` and query-history database are 0640, and `gravity.db` is 0664. The legacy directory remains mounted with its existing activation setting; the role does not enable it. Upstream internet access and running Caddy are required for the final checks. DNS/HTTP checks do not test every filtering rule, DHCP behavior, IPv6 resolution, or an authenticated admin login. The separately managed adapter can verify authenticated Pi-hole API access.

Validation on 2026-10-19: syntax, production preview, deployment and repeat passed with `changed=0`, `failed=0` (live runs `ok=19`). Unbound preflight, native DNS syntax validation, public DNS over UDP/TCP, all six local IPv4 records over both protocols, and trusted HTTPS administration passed. The running image, host networking, shared memory, mounts, environment, saved DNS settings, password hash, entire TOML contents, and checked file ownership/modes were verified unchanged. Disposable fixtures rejected missing settings, corrupt gravity data, an unsafe upstream, enabled conditional forwarding, and invalid DNS syntax before deployment. Authenticated API access through the existing adapter and all 17 production health checks passed afterwards. A full new-host rebuild and every filtering rule were not exercised.

## Pi-hole adapter deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook pihole-adapter.yml --syntax-check
ansible-playbook pihole-adapter.yml --check --diff
ansible-playbook pihole-adapter.yml
# Rebuild after changing app.py, requirements.txt, or Dockerfile:
ansible-playbook pihole-adapter.yml -e homelab_pihole_adapter_build=always
```

Restore `apps/pihole-adapter/.env`, prepare the `proxy` network, and start Pi-hole first. Versioned `.env.example` lists the required settings without credentials. The role validates nonempty credentials, an HTTP(S) base URL, and timeout/cache settings without displaying values. It preserves `.env` contents and ownership and restricts its mode to 0600. The adapter has no persistent data volume. The current image runs as root; source and environment files belong to the homelab account.

Unlike the registry-image services, this service is built locally. `homelab_pihole_adapter_build` defaults to `policy`: reuse an existing image, or let Compose build a missing image. Use `always` explicitly to apply changed sources; restore the default policy for unchanged repeat runs. A fresh build needs registry/package-network access. `.dockerignore` excludes local `.env` files from the build context. Installed sources, dependency versions, and container runtime are described by the existing Dockerfile and requirements file.

Post-deployment checks use the private `proxy` address: `/health` must return `ok: true`, and `/pihole-summary` must return `status: online`, exercising Pi-hole authentication and statistics retrieval. Summary responses and container details are hidden from Ansible output. These checks do not expose a new host port or public route. Session tokens and upstream error details are excluded from application logs and error responses; useful status codes and exception types remain. Three tests cover token privacy through the session lifecycle, malformed authentication responses, and summary exceptions. Run them against the built image with no networking:

```bash
cd ~/Documents/homelab
sudo docker run --rm --network none --entrypoint python \
  --mount type=bind,src="$PWD/apps/pihole-adapter/test_app.py",dst=/app/test_app.py,readonly \
  pihole-adapter-pihole-adapter -B -m unittest test_app -v
```

Backrest/Unbound/adapter validation on 2026-10-19: all three playbooks passed syntax, preview, deployment and unchanged default-policy repeats. Backrest reconciled once (`changed=1`), then its final run with the active-operation guard passed with `changed=0`; repository password verification, HTTPS UI and saved history checks passed. Unbound reported `changed=0` throughout, including syntax validation and UDP/TCP DNS checks. The adapter was rebuilt for the privacy fix and its `.env` restricted to 0600 (`changed=2`); repeat reported `changed=0` and authenticated summary checks passed. All three privacy regression tests passed against the new image, and the deployed application source matches the checkout. Disposable fixtures verified missing Backrest recovery files, missing adapter environment, and invalid Unbound syntax stop before deployment. All 17 production health checks passed afterwards. These checks do not exercise a new-host build, complete repository integrity, or external recovery.

## Matrix deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook matrix.yml --syntax-check
ansible-playbook matrix.yml --check --diff
ansible-playbook matrix.yml
```

Restore `apps/matrix/.env` (or supply its existing password through Vault as described below), the complete `data/matrix/synapse` directory (including signing key, logging configuration and media), and a valid PostgreSQL 16 cluster at `data/matrix/postgres`. The role requires `PG_VERSION`, `global/pg_control`, `base/`, and the saved homeserver configuration; it refuses to initialize an empty replacement cluster. A logical dump must first be restored into a compatible cluster using the documented recovery procedure. Raw files copied from a running database are not an established recovery source. The role does not restore dumps or run database migrations itself; Synapse's normal startup can perform its own migrations when its image changes.

The saved `server_name` must remain `pentagonlab.org`, while its public URL is `https://matrix.pentagonlab.org`. The role checks this identity, PostgreSQL major version, matching `.env`/Synapse database credentials, the `psycopg2` backend and `postgres:5432` connection settings. Configured signing-key, log-config and media paths must remain within the restored `/data` mount; missing files and unsafe paths stop deployment. System Python needs PyYAML (`python3-yaml`, included in host prerequisites). The current Compose definition, images, private network, mounts, dependency order and loopback-only `127.0.0.1:8008` binding are validated before deployment.

Synapse configuration is checked by the installed image as UID 991 with read-only `/data` and networking disabled. A separate disposable Synapse-image process on `matrix-network` uses the saved credentials for an actual PostgreSQL connection, restricted to read-only queries. It checks UTF8/C/C locale, required Synapse tables and a positive schema version without reading user/message records or printing credentials. This runs before changing an already running database. The role then deploys PostgreSQL only, waits for health, rechecks authentication/schema, and finally deploys Synapse only. Stopped/new-host database checks are deferred until the restored PostgreSQL service starts. Empty schemas and wrong actual database passwords stop Synapse deployment.

The role restricts `.env` to 0600, the top-level Synapse directory to 0700, and its homeserver configuration, signing key and log configuration to 0600. Existing ownership is preserved by default, and UID 991 ownership is checked before restricting Synapse files; use sudo for host-side inspection/editing afterward. Current PostgreSQL storage remains UID 70, mode 0700, with no recursive ownership changes. This protects media and other existing files through the private parent directory. By default runtime file contents are preserved and no Vault password is required. Optional Vault rendering manages only the Matrix `.env` as the configured homelab owner/group; it does not rotate the database password or render Synapse configuration, signing keys or identity. Deliberate edits to runtime Synapse configuration require a controlled Synapse restart to take effect.

Installed images are reused (`pull: missing`, `build: never`, `recreate: auto`, no orphan removal). Defaults are `postgres:16-alpine` and `matrixdotorg/synapse:latest`; verify image compatibility before upgrading. The role checks local `/health` and the client versions API, then the public versions API with certificate verification through the existing Cloudflare Tunnel. For bootstrap without a running tunnel, use `-e homelab_matrix_check_public=false` and rerun with the default after the tunnel is online. Public checks do not configure the tunnel or prove authenticated messaging, federation, media recovery or calling support. Coturn remains retired.

Database recovery procedure: [operations](../OPERATIONS.md#matrix-database-backups). Upstream requirements: [Synapse backups](https://element-hq.github.io/synapse/develop/usage/administration/backups.html).

### Matrix password recovery with Ansible Vault

Import the existing password locally, using the same Vault unlock password already kept in your password manager for Portainer:

```bash
cd ~/Documents/homelab/ansible
python3 -B import-matrix-vault.py
ansible-playbook matrix.yml -e @vars/matrix.vault.yml --ask-vault-pass --check --diff
ansible-playbook matrix.yml -e @vars/matrix.vault.yml --ask-vault-pass
# An unchanged repeat should report changed=0:
ansible-playbook matrix.yml -e @vars/matrix.vault.yml --ask-vault-pass
```

The importer reads `MATRIX_POSTGRES_PASSWORD` from the existing `.env` and writes only encrypted `vars/matrix.vault.yml` (0600), refusing an existing output or symlink. It preserves the source and removes incomplete output on encryption failure. It accepts one assignment with a nonempty password containing only letters, numbers, `_ . ~ + / = -`; interpolation, multiline values, placeholder passwords and unrelated assignments are refused. The credential-free `vars/matrix.vault.example.yml` documents the variable name. No real password belongs in a command argument or chat. `--vault-password-file` is available for private disposable tests or an existing secure credential workflow; do not create a permanent unlock file on this server just to avoid the prompt.

When `vault_matrix_postgres_password` is supplied, the role privately validates Compose using that value and requires it to match the restored Synapse configuration before writing `.env`. A running database is authenticated with the restored credentials before rendering. It refuses to discard unrelated environment settings. After recovery checks, the role can recreate a missing `.env` or render the existing password with mode 0600, suppressing secret output and diffs. Supplying a different password is rejected; database password rotation requires a separate coordinated operation.

Keep the encrypted variables file with your recovery material and its unlock password outside this server. The variables file and rendered `.env` are ignored by Git. This does not create an external backup, replace Synapse's saved configuration password, or remove the application's need for plaintext runtime credentials.

Importer regression checks use disposable values and real Vault encryption:

```bash
python3 -B -m unittest discover -s ansible/tests -p 'test_*.py' -v
```

The permanent Matrix Vault is unlocked with the user-entered password. On 2026-10-21 the user created it locally and supplied a successful production run: `ok=32`, `changed=0`, `unreachable=0`, `failed=0`. Permanent Vault decryption, environment rendering, authenticated database/schema checks, and local/public Matrix APIs all passed. The unlock password was not shared with the assistant.

Vault extension validation on 2026-10-19: all four importer regression tests passed, including real encryption/decryption, mode 0600, unchanged source, overwrite/symlink refusal, invalid-input rejection and incomplete-output cleanup. Eight isolated pre-write/template cases verified missing-environment recreation with Vault and rejection of missing credentials, mismatched/empty/placeholder/multiline passwords, unrelated settings and environment symlinks. These fixtures exercised the actual recovery guards/template, without deploying fixture containers. Production preview using a disposable encrypted Vault passed (`ok=27`, `changed=1`, `failed=0`); deployment rendered only `.env` (`ok=32`, `changed=1`, `failed=0`), and repeat passed (`ok=32`, `changed=0`, `failed=0`). Effective database credentials, production container IDs/images, Synapse configuration and signing key were verified unchanged. All 18 health checks passed. Temporary Vault/unlock files were removed; the permanent `vars/matrix.vault.yml` had not yet been created at that point; its successful user-run production deployment is recorded above on 2026-10-21.

Validation on 2026-10-19: syntax and production preview passed; deployment restricted the three permission groups (`changed=3`), and repeat/final verification reported `ok=31`, `changed=0`, `failed=0`. Authenticated database/schema checks, native configuration validation, local health/client API and public client API all passed. Existing images, mounts, ports, private-network ID, environment, configuration/secret contents and file owners were verified unchanged. Five disposable recovery cases rejected missing cluster control, incompatible major version, mismatched secrets, missing signing key and changed server identity before deployment. A separate temporary PostgreSQL instance with no published ports rejected an empty schema and incorrect password, and accepted the minimal expected fixture schema with correct credentials; its container/network/storage were removed. Final secret-file modes and all 17 production health checks passed. A subsequent isolated Synapse startup from backup passed; see [the application recovery report](../reports/2026-10-19-synapse-rebuild.md). Replacement-host provisioning remains untested.

## Cloudflare Tunnel deployment

```bash
cd ~/Documents/homelab/ansible
ansible-playbook cloudflared.yml --syntax-check
ansible-playbook cloudflared.yml --check --diff
ansible-playbook cloudflared.yml
```

Restore the complete ignored `data/cloudflared` directory, including `config.yml` and the named tunnel's credential JSON. The role validates a matching tunnel UUID, a nonempty account tag and correctly sized base64 secret, an in-mount credential path, Matrix's existing origin, and the final HTTP 404 catch-all. It does not create a tunnel, log in, rotate credentials, or change DNS/Cloudflare account settings. System Python needs PyYAML. Existing non-Matrix ingress entries are preserved.

Compose must retain host networking and the read-only `/etc/cloudflared` mount. The named tunnel command now explicitly binds its metrics/readiness listener to `127.0.0.1:20241`, replacing the observed wildcard binding. No host port or public route is added. The role rejects token/credential environment overrides and checks the official image's non-root UID/GID 65532:65532. Restored file ownership remains unchanged, while the tunnel directory becomes mode 0750 and config/credential files mode 0640, all with numeric service GID 65532. The host owner can still edit them; the daemon has read access, and other local users lose access. No recursive ownership changes are made.

Native ingress validation and Matrix rule selection run in disposable containers with networking disabled, the restored mount read-only, and the daemon's UID/GID. A Matrix URL shadowed by an earlier rule is rejected. Preview performs these checks when the image is installed; otherwise it predicts the image download and defers native validation. Files need to be readable by the service identity for preview's native checks; a live run applies the declared access modes first. Saved config and credentials are not rendered or replaced. Intentional runtime ingress edits require a controlled tunnel restart to take effect.

A live run checks local Synapse health, deploys only Cloudflared (`pull: missing`, `build: never`, `recreate: auto`, no orphan removal), and waits for this connector's loopback `/ready` endpoint. It then checks public Matrix versions with trusted TLS and the existing secondary route `https://vladjik.dev/`. That application's local origin at port 9090 is managed outside this repository; restore/start it separately, or override `homelab_cloudflared_extra_public_urls` with the intended check list. Matrix is expected at `http://127.0.0.1:8008`; deploy it before the tunnel. The metrics argument change requires one connector recreation/reconnect, while unchanged repeats reuse the running connector.

These checks establish current connector readiness and HTTP routing from this host; they are not independent off-host outage monitoring or authenticated Matrix messaging tests. Reference: [Cloudflare locally managed tunnel validation](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/).

Validation on 2026-10-19: syntax, preview and deployment passed (`changed=3` for directory access, file access and connector reconciliation); the repeat reported `ok=24`, `changed=0`, `failed=0`. Native ingress validation and exact Matrix rule selection passed; local origin, connector readiness, public Matrix versions, and the existing secondary public route all passed. The installed image, non-root user, host networking, read-only mount, environment, restored configuration/credential contents and file owners were preserved. The credentials and directory were verified private to owner/service group, and `ss` confirmed metrics listens only on `127.0.0.1:20241`. Five disposable cases rejected missing credentials, mismatched tunnel identity, invalid secret, wrong Matrix origin and a shadowing rule before deployment. All 17 production health checks passed. All eleven declared Compose projects now have deployment playbooks. A subsequent isolated Synapse startup from backup passed; see [the recovery report](../reports/2026-10-19-synapse-rebuild.md). A complete replacement-host rebuild remains outstanding.

## Monitoring and database backup jobs

```bash
cd ~/Documents/homelab/ansible
ansible-playbook scheduled-jobs.yml --syntax-check
ansible-playbook scheduled-jobs.yml --check --diff
ansible-playbook scheduled-jobs.yml
# An unchanged repeat should report changed=0.
ansible-playbook scheduled-jobs.yml
```

The `scheduled_jobs` role installs eleven versioned Python scripts, `monitoring/config.json`, and all eight service/timer units, including weekly isolated backup recovery. Sources remain in `scripts/` and `monitoring/`; edit those canonical files and rerun the playbook. The units' existing checkout path is replaced with `homelab_repo_path` during installation. The scripts require `homelab_data_path` to be `<repo>/data`, and the checkout path must not contain spaces or systemd specifiers. This is tested with the local inventory; remote host provisioning remains separate work.

Run `prepare.yml` first on a replacement host, restore Caddy's local CA and `data/monitoring/matrix.json`, and restore/start the application containers, including `matrix-postgres`. The role checks systemd, Docker, curl, Restic, Python YAML support, the running database container, installed Synapse, the local backup repository and its lock directory, Backrest configuration, and restored notification credentials before installation. It preserves the existing alert room and token; it does not create a room, rotate credentials, or require the Portainer Vault password. Missing recovery files stop the playbook. Restored credential contents, alert queues/cursors, and previous database dumps are preserved.

Scripts and monitoring configuration are installed as the configured homelab account with mode 0644; their directories are 0755. The units run scripts through `/usr/bin/python3 -B`. Notification credentials remain root-owned 0600; the notification directory, database dump directory, and `/var/lib/homelab-monitor` plus `/var/lib/homelab-recovery` are root-owned 0700. No recursive ownership changes are made. Private state files are created by the existing scripts/systemd policy.

All eight units are staged in a temporary directory and checked together with `systemd-analyze verify` before replacing installed units. Staging is also performed and cleaned up during preview. A handler reloads systemd only when installed units change. The role then enables and starts the four timers and verifies their active/enabled status. In preview, timer activation is predicted for existing unit files; activation of newly installed timers requires a live run. Existing services are not manually triggered by the playbook; newly activated timers can immediately run jobs due under their normal schedules.

Schedules remain defined in `monitoring/*.timer`:

| Timer | Schedule |
| --- | --- |
| `homelab-monitor.timer` | Every five minutes; initial run two minutes after boot |
| `homelab-matrix-status.timer` | Every 15 seconds; initial run 30 seconds after boot |
| `homelab-matrix-backup.timer` | Hourly, with up to three minutes of random delay and catch-up after downtime |
| `homelab-recovery.timer` | Sunday 04:30–05:00 Europe/Warsaw; catch-up after downtime |

Read-only verification and an optional fresh database dump:

```bash
sudo python3 -B ../scripts/monitor.py --check
systemctl list-timers homelab-monitor.timer homelab-matrix-status.timer homelab-matrix-backup.timer homelab-recovery.timer
sudo systemctl start homelab-matrix-backup.service
sudo journalctl -u homelab-matrix-backup.service -n 10 --no-pager
```

Monitoring behavior and coverage limits: [monitoring README](../monitoring/README.md). Database recovery: [operations](../OPERATIONS.md#matrix-database-backups). Systemd management reference: [Ansible systemd_service](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/systemd_service_module.html).

Weekly recovery extension validated on 2026-10-19: syntax and staged unit validation passed; preview predicted the recovery units and script permissions. Deployment passed (`ok=34`, `changed=3`, `failed=0`); repeat passed (`ok=33`, `changed=0`, `failed=0`). The installed recovery service completed the full snapshot/database/Synapse workflow with `Result=success` and exit 0. An overlapping wrapper invocation was refused without replacing the active result. All four timers are enabled and active. Recovery status/log modes are 0600 inside a 0700 directory; temporary restore resources were removed and all 18 production checks passed. All 20 Python regression tests passed, including failed/interrupted result publication and stale/stuck recovery alert decisions. External monitoring was deferred by the user on 2026-10-19; its inactive settings are retained for future use in [the setup notes](../monitoring/EXTERNAL_MONITORING.md).

Validation on 2026-10-19: syntax, unit validation, and production preview passed. Deployment normalized script/configuration and directory permissions (`changed=3` task groups); the repeat reported `ok=29`, `changed=0`, `failed=0`. Existing script/configuration/unit-source and notification credential contents were verified unchanged. All three timers were active and enabled; their services' latest runs succeeded. An explicit database-backup service run published a new private dump and validated its archive index; all 17 health checks then passed. A temporary empty-checkout preview confirmed missing credentials stop installation before creating directories. All 17 existing Python regression tests passed. These checks do not establish a full replacement-host rebuild or end-to-end database restoration.

## Managed settings and recovery staging

The current seven-item action list and local secret finish step are in [ACTION_LIST.md](../ACTION_LIST.md). Managed Synapse/tunnel configuration and adapter Vault support are documented in [managed configuration](MANAGED_CONFIGURATION.md). New configuration playbooks validate candidates before writing and preserve restored identities/secrets; the original deployment playbooks still work with restored runtime files.

[Recovery staging](RECOVERY_STAGING.md) builds a source archive and encrypted, verified latest-snapshot repository, then copies them into a new inactive directory on an identity-verified replacement. It refuses overwrites and does not extract or deploy anything. Actual separate-host staging remains untested.

The weekly recovery service now includes disposable-account Matrix and Vaultwarden workflows. Production adoption, native reconstruction fixtures, encrypted staging, 45 regression tests and all 18 health checks passed; see [the batch report](../reports/2026-10-21-action-batch.md). Permanent Synapse/adapter Vault imports and Portainer's actual user-managed Vault repeat await the local unlock helper; they are not marked complete.
