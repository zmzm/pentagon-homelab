# Replacement-host preparation

Status: the separate SSH inventory and read-only target verification are implemented. SSH validation was exercised through a disposable loopback-only SSH listener on the current host. Provisioning a genuinely separate machine and rebuilding all services there remain untested.

The default `inventory.ini` still targets only the current local host. No replacement address, SSH credential or active private inventory has been created. `inventory.ssh.example.yml` contains placeholders; copy it to the Git-ignored `inventory.ssh.yml` when a target is available.

## Prepare the target and controller

The target needs a supported 64-bit Debian-family OS, systemd, Python 3 at `/usr/bin/python3`, an SSH login and sudo access. The configured homelab owner and group must already exist. SSH authentication uses your existing key/agent; use `--ask-pass` only if password login is needed and supported by the controller. Use `-K` when sudo needs a password. Keep all passwords out of the inventory and chat.

On the controller, use the repository's installed Ansible and pinned `community.docker` collection. Run commands from `ansible/` to load its configuration.

```bash
cd ~/Documents/homelab/ansible
cp inventory.ssh.example.yml inventory.ssh.yml
chmod 600 inventory.ssh.yml
```

Edit the private copy with the target's SSH address, port and user. Read the target hostname and machine ID from its trusted console (`hostname` and `cat /etc/machine-id`) and fill in the expected identity fields locally. Check the SSH host-key fingerprint against the console before accepting it in your controller's SSH known-hosts file. Host-key verification remains enabled; do not bypass a changed-key warning.

The example retains `pentagon-admin` and `/home/pentagon-admin/Documents/homelab`, matching the current Compose bind mounts. The SSH administrator may be a different account, but the configured homelab owner/group must exist. If the homelab account or checkout path changes, review and update Compose bind mounts and other absolute paths too: overriding inventory variables alone does not rewrite Compose files.

## Verify before provisioning

```bash
ansible-inventory -i inventory.ssh.yml --graph
ansible-playbook -i inventory.ssh.yml remote-preflight.yml --check
```

The playbook requires exactly one target in `homelab_replacement`, an SSH connection, non-placeholder target details, and an expected machine ID. It verifies hostname/machine ID, sudo access, Debian-family OS, ARM64/x86-64 architecture, systemd, existing owner/group, a usable checkout path and at least 2 GiB free. Adjust `homelab_remote_minimum_free_gib` upward for actual backup/image capacity; this minimum is not a recovery capacity estimate. It reports whether the checkout, Docker binary and an official Docker source entry are present. Source-entry detection does not validate apt signing keys, package availability or the daemon.

The repository may be absent at this stage; no checkout, packages, networks, services or restored data are created. Ansible's normal temporary module staging is cleaned up after execution. The command also runs in preview mode because it is read-only. Detailed target identity stays out of normal playbook output.

`site.yml` imports this verification for targets in `homelab_replacement`, so existing preparation and service playbooks automatically verify such targets before their usual preflight. Local-inventory runs skip the SSH gate. Explicitly invoking `remote-preflight.yml` with the local inventory fails before connecting.

## Continue on a verified replacement

1. Confirm the target uses supported Debian 12/13 or Ubuntu 22.04/24.04/26.04 LTS on ARM64/AMD64. `prepare.yml --tags prerequisites` now creates a missing official Docker apt repository, verifies its signing key, refreshes metadata when needed and installs missing packages. Matching existing sources and installed versions are preserved. Conflicting Docker/runtime packages or ambiguous apt sources stop preparation for review; none are removed automatically.
2. Check out this repository on the target at the configured absolute path, owned by the configured account. A private repository needs your own Git access. The existing `site.yml` requires the checkout before host preparation can run.
3. Review and run host preparation using the private SSH inventory. When Docker is absent, a full preview cannot simulate installing it and then querying the daemon: install prerequisites as a separate stage, then preview the directory/network stage. This can start Docker and existing containers with restart policies; use a genuine intended replacement target.
4. Restore the runtime configuration, credentials, signing keys, Caddy CA and application data according to [recovery operations](../OPERATIONS.md#backup-recovery-verification). Recover Matrix from the consistent logical dump into a compatible initialized cluster; copied live PostgreSQL files are not the established recovery source. Service roles intentionally reject missing recovery state.
5. Deploy the eleven projects in the documented [deployment order](../ANSIBLE_MIGRATION_PLAN.md#phase-5-compose-deployment). Pass `-i inventory.ssh.yml` explicitly for each playbook. Use the controller's encrypted Vault files and interactive unlock prompt where needed.
6. Install `scheduled-jobs.yml` after the repository, local backup repository, credentials and application containers have been restored. Run the documented initial recovery verification and health checks on the replacement.

Example preparation commands, only after target identity and prerequisites have been reviewed:

```bash
ansible-playbook -i inventory.ssh.yml prepare.yml --tags prerequisites
ansible-playbook -i inventory.ssh.yml prepare.yml --tags directories,networks --check --diff
ansible-playbook -i inventory.ssh.yml prepare.yml --tags directories,networks
```

This is preparation for remote recovery, not a fully automated bare-metal rebuild. It does not install the OS, configure SSH/sudo accounts, clone the checkout, transfer backups, automate destructive restores, change DNS/tunnel routing or prove recovery on new hardware. Independent outside monitoring remains deferred by the user.

References: [Ansible inventories](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html), [SSH and host-key checking](https://docs.ansible.com/projects/ansible/latest/user_guide/connection_details.html).

## Validation — 2026-10-21

Inventory parsing and syntax validation passed. A temporary SSH daemon bound only to loopback, using disposable host/client keys and a private known-hosts file, exercised real SSH authentication and the actual preflight. Direct preflight, preview and the shared `site.yml` path passed with `changed=0`. Wrong machine ID (direct and shared preflight), wrong hostname, a local connection, placeholder address, multiple targets, a changed SSH host key and use of the default local inventory were rejected. The temporary listener, keys and inventories were removed; production SSH configuration was not edited.

All seven Ansible importer/target-guard regression tests passed. Existing local `site.yml` passed with `ok=4`, `changed=0`, `failed=0`, skipping the four remote-only tasks; preparation, Matrix and scheduled-job playbooks passed syntax validation. All 18 production health checks passed afterwards. No active replacement inventory was created. These checks validate SSH transport and target verification against a temporary listener on the existing host; they do not establish provisioning or recovery on another machine.
