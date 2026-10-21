# Managed Synapse and tunnel configuration

`matrix-config.yml` and `cloudflared-config.yml` adopt settings from `roles/service_configuration/defaults/main.yml`. They validate candidates using the exact installed application image, no network, read-only service data and a private temporary candidate. Candidate files are removed afterwards. Both playbooks then run the existing service deployment and health checks.

Semantically unchanged configurations keep their original bytes and do not restart services. Changed validated settings are written atomically with private permissions; a running service is restarted and checked for readiness. If activation fails, existing prior configuration is restored and restarted when available. The rollback branch is implemented but a forced production failure was not exercised. The selected container must actually bind the configuration directory, preventing an unrelated service from being restarted.

```bash
cd ~/Documents/homelab/ansible
ansible-playbook matrix-config.yml --check
ansible-playbook matrix-config.yml
ansible-playbook cloudflared-config.yml --check
ansible-playbook cloudflared-config.yml
```

## Synapse secrets and identity

The public settings contain no passwords. Existing `registration_shared_secret`, `macaroon_secret_key`, `form_secret` and database password are retained privately from the current file. To recreate a missing configuration, supply `vault_matrix_synapse_secrets` (the first three values) and `vault_matrix_postgres_password`, together with the restored signing key, logging configuration, media and database state. An image must be available for preview; live recovery can obtain a missing expected image.

Changing the server identity, signing-key path, database connection/backend or an existing secret is rejected. Unmodeled top-level settings are refused rather than discarded. This role is not a password/identity rotation tool. `homelab_matrix_homeserver` is the complete public configuration mapping; review changes in version control before applying them.

Create the encrypted file using the local finish step in [the action list](../ACTION_LIST.md), or individually:

```bash
sudo python3 -B import-service-vault.py synapse
ansible-playbook matrix-config.yml -e @vars/synapse.vault.yml --ask-vault-pass
```

The importer preserves runtime files and creates only encrypted output. When run with sudo, output is made readable only by the invoking user. It refuses to overwrite an existing output. On 2026-10-21 the user completed the permanent encrypted import locally; both managed Matrix production runs passed with `ok=51`, `changed=0`, `failed=0`. The adapter permanent import and both production runs also passed (`ok=20`, `changed=0`, `failed=0`).

## Tunnel routing

The tunnel configuration is built from the versioned `homelab_cloudflared_configuration` routing mapping and exactly one restored regular credential JSON. Its UUID and credential path are derived from that file. Existing identity/path changes or unmodeled settings are rejected. Native ingress validation and Matrix rule selection run before writing. Missing credentials are not generated; the Cloudflare account, DNS and tunnel identity are preserved.

## Adapter Vault

`pihole-adapter.yml` accepts `vault_pihole_adapter_environment`, containing exactly `PIHOLE_BASE_URL`, `PIHOLE_PASSWORD`, `REQUEST_TIMEOUT` and `SUMMARY_CACHE_TTL`. It validates types, URL and timeouts, rejects implicit password rotation and unrelated existing assignments, then renders `.env` as 0600. Single quotes, backslashes and line breaks are refused for literal environment rendering. Credentials and diffs stay out of output. Authenticated Pi-hole summary verification follows deployment.

```bash
python3 -B import-service-vault.py pihole-adapter
ansible-playbook pihole-adapter.yml -e @vars/pihole-adapter.vault.yml --ask-vault-pass
```

Without supplied Vault values, the existing restored `.env` is preserved as before. A missing `.env` can be rendered from Vault in a live run; full preview still requires the environment file for Compose's `env_file` resolution.
