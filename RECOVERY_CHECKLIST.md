# Replacement-server recovery checklist

Prepared 2026-10-21. This joins the tested recovery components into a rehearsal procedure. A complete replacement-server rebuild has **not** been tested. The existing server stays active until a deliberate cutover; a rehearsal must keep the copied tunnel, alert sender, backup schedules and update automation inactive.

## 1. Gather the recovery material

- [ ] Obtain the public source archive or checkout, including the current improvements. A Git commit alone may omit uncommitted work.
- [ ] Obtain an intact encrypted Restic repository and its unlock password from your password manager. The source archive does not contain application data or the repository password.
- [ ] Obtain the encrypted Ansible variables separately: `portainer.vault.yml`, `matrix.vault.yml`, `synapse.vault.yml`, `pihole-adapter.vault.yml`, and their corresponding unlock passwords. They are Git-ignored and excluded from the public staging archive. Do not assume all files use the same password.
- [ ] Retain SSH/Git access and access to the Cloudflare account for an eventual cutover. Keep passwords out of commands and chat.

The local Restic repository is currently the verified backup source. External backup and outside monitoring remain deferred. A bundle on the same server is useful staging material but cannot survive loss of that server's storage.

## 2. Prepare and identify the replacement

Follow [replacement-host preparation](ansible/REMOTE_PROVISIONING.md) to install the OS, establish SSH/sudo access and confirm hostname, machine ID and SSH host-key fingerprint. Use a supported architecture and enough storage for the encrypted repository, restored data, container images and temporary recovery tests; the preflight's 2 GiB minimum is not sufficient sizing guidance.

- [ ] Preserve the expected account and checkout path, or review every absolute bind mount before changing them: `/home/pentagon-admin/Documents/homelab`.
- [ ] Create the controller's private SSH inventory and pass its explicit `-i inventory.ssh.yml` to every remote playbook. The default inventory points at the existing local server.
- [ ] Run read-only remote preflight before any preparation.
- [ ] Install the checkout and prerequisites, then prepare directories and Docker networks as described in the linked guide. Confirm the pinned Ansible collection from `ansible/requirements.yml` is installed on the controller.

For a rehearsal, isolate the target from production traffic and do not reuse the live server's LAN address. Initially provide working DNS independently of the Pi-hole instance being recovered. Review local `home.arpa` resolution and client trust in the restored Caddy CA before HTTPS checks.

## 3. Stage and restore privately

Use [recovery staging](ansible/RECOVERY_STAGING.md) to build and transfer a new bundle, verify its hashes and validate the encrypted repository. Staging deliberately does not extract files or deploy applications.

- [ ] Select and record the exact snapshot and its timestamp. Restore into a new private temporary directory first; inspect the saved layout under `userdata/homelab` before copying anything into the replacement checkout.
- [ ] Preserve numeric ownership and private permissions. Never merge recovered databases into running application directories.
- [ ] Restore the complete service state below, rather than only the files checked by a deployment role.

| Component | Required recovery state |
| --- | --- |
| Caddy | Runtime data, including the original local CA and its private key, plus the versioned Caddyfile |
| Pi-hole / Unbound | Complete saved Pi-hole directories and versioned Unbound configuration |
| Pi-hole adapter | Existing private `.env` or its encrypted adapter variables |
| Homepage / Portainer | Complete runtime configuration/database and Portainer environment key or encrypted variables |
| Vaultwarden | Database and applicable WAL, attachments, Send files, saved configuration and RSA signing key |
| Backrest | Configuration, application databases, and the encrypted Restic repository at `backups/restic` |
| Matrix | Consistent logical dump, Synapse configuration, signing key, log configuration, media, and matching database password |
| Cloudflare Tunnel | Original credential JSON and routing configuration; keep the connector inactive during rehearsal |
| Monitoring | Private `data/monitoring/matrix.json`; keep notifications inactive during rehearsal |

For Matrix, initialize a fresh compatible PostgreSQL 16 cluster and restore the logical dump before deploying Synapse. The current isolated verifier demonstrates this process with `pg_restore`; it deletes its temporary database and is not a production restore command. A reviewed replacement-specific database restore remains a manual step. Do not treat copied live PostgreSQL files as the verified recovery source or let Compose initialize an empty replacement database accidentally.

For Vaultwarden, match database/WAL handling to the backup method and keep the application stopped during installation of restored files. See [recovery operations](OPERATIONS.md#backup-recovery-verification) and the service notes in [the Ansible guide](ansible/README.md).

## 4. Deploy and validate in dependency order

Run each dedicated playbook with the replacement inventory, reviewing its prerequisites first. Preview needs restored files and, for some checks, installed images; it cannot simulate every missing prerequisite.

1. Caddy: use `homelab_caddy_check_routes=false` for initial startup before upstreams exist.
2. Unbound, then Pi-hole, then the Pi-hole adapter.
3. Homepage, Portainer, Vaultwarden and Backrest.
4. Matrix after its database restore; use `matrix-config.yml` with the encrypted Synapse variables if configuration reconstruction is needed.
5. Rerun Caddy with its normal route checks after all upstreams are available.
6. At an intentional cutover only: activate Cloudflare Tunnel, install scheduled jobs, then deploy Watchtower last.

The interview application (`nextapp:4000`, also reached through the tunnel's port 9090 route) is outside this repository. Recover its separate project and data before expecting every Caddy/tunnel route check to pass. Do not remove a failed route check to conceal that missing dependency.

Backrest may resume configured schedules when started. During a rehearsal, review and disable automatic backup actions in the replacement's copied configuration before starting it. Do not connect a rehearsal Cloudflare connector to the live tunnel: it can receive real traffic. Scheduled jobs include Matrix notifications and must also remain inactive during rehearsal.

## 5. Record evidence before cutover

- [ ] Verify trusted HTTPS, DNS over UDP/TCP, authenticated adapter summary and each deployment role's normal health checks.
- [ ] Check actual user access: Vaultwarden login/decryption and Matrix client login/history/media. Existing-user encrypted-content recovery is not proven by the synthetic tests.
- [ ] Run the isolated application verification on the replacement after its local backup repository and required containers/images exist: `sudo python3 -B scripts/verify-backup.py --matrix-workflows --vaultwarden-app`.
- [ ] Repeat deployments; investigate unexpected changes instead of assuming success means repeatability.
- [ ] Record snapshot ID, target identity, image versions, results and any missing data in a recovery report. Keep private logs private.
- [ ] Plan one active production writer, LAN/DNS changes, tunnel activation and a fallback before moving traffic. Keep the original server available until the replacement passes acceptance checks.
- [ ] After cutover, install/verify the scheduled jobs, run all 18 health checks and verify a new local backup and recovery result.

The next milestone is a rehearsal on an identified spare machine or suitable isolated VM. No replacement target has been configured yet; this checklist does not claim that milestone is complete.
