# Authorized improvement batch — 2026-10-21

The seven requested actions are tracked in [ACTION_LIST.md](../ACTION_LIST.md). Automated implementation and verification are complete for managed configuration, adapter Vault support, expanded application recovery and encrypted recovery staging. The user completed the permanent secret imports and Portainer user-managed Vault repeat locally; all seven actions are complete within the documented scope.

## Managed service configuration

Synapse and Cloudflare Tunnel settings now have versioned public mappings and dedicated managed-configuration playbooks. Secrets, signing identity and tunnel credentials are preserved. Candidates are validated natively with the exact installed images, read-only restored state and no network before any write. Unchanged parsed configuration preserves its original bytes and avoids a restart. Mount matching prevents the wrong container from being restarted. Changed live configuration has a readiness check and a prior-configuration rollback path; a forced live rollback was not exercised.

Production adoption and repeat passed for Matrix (`ok=49`, `changed=0`, `failed=0`) and Cloudflared (`ok=43`, `changed=0`, `failed=0`), including their existing deployment and service checks. Configuration/signing-key bytes remained unchanged. After adding the final mount guard, previews again passed with `changed=0`, `failed=0`.

Missing Synapse and tunnel configurations were reconstructed in private directories using stopped, network-isolated fixture containers and real native parsers. Synapse used a disposable encrypted Vault containing the original secrets; tunnel identity came from copied credential JSON. Generated configurations matched production semantically. Reconstruction reported `changed=1`; repeat reported `changed=0` for both. No fixture was started and production was not restarted. Secret copies, Vault/unlock files and fixture containers were removed.

## Adapter Vault

The adapter importer encrypted its existing settings into a private disposable Vault. Production deployment passed with `ok=20`, `changed=1`, `failed=0`, normalizing only the private environment format; the repeat reported `changed=0`. Health and authenticated Pi-hole summary checks passed. The disposable Vault/unlock file was removed. The permanent user-managed adapter Vault was subsequently imported and both production runs passed (`ok=20`, `changed=0`, `failed=0`).

## Application recovery

The latest tested snapshot was `4f1f7ed4`, dated `2026-10-21T06:00:34+02:00`. Restic recovered 3549 files/directories (836.030 MiB), with 3071 files content-verified. Required recovery files and Vaultwarden SQLite integrity passed.

Recovered Vaultwarden 1.37.2 started without external networking or host ports. Its UI and health checks passed. A disposable account registered and logged in, then stored, retrieved, decrypted and synced a synthetic encrypted item. Database integrity and expected row-count changes were checked; the saved RSA signing-key bytes were preserved. Existing user contents were not decrypted or logged.

The Matrix dump restored into a fresh isolated PostgreSQL instance: 169 public tables, 4 users, 6 rooms, 422 events, schema version 93. Recovered Synapse passed health/client/server-key checks with the original signing key and 79 restored media files present. Two disposable accounts registered and logged in, exchanged a message in a private unfederated room, and uploaded/downloaded synthetic media through authenticated APIs. All synthetic writes were confined to the restored copies.

Both application tests enforce loopback-only interfaces before synthetic writes. Containers had no published ports or production mounts; test containers were excluded from Watchtower. Temporary databases, restored data and containers were removed. These checks do not establish existing-user master-password decryption, Matrix end-to-end encryption/federation, browser/mobile client behavior or a full separate-host rebuild.

The installed weekly recovery service now runs both workflows. Deployment passed (`ok=33`, `changed=1`, `failed=0`), repeat passed (`changed=0`), and the installed systemd service completed with `Result=success`. Private status and latest log remain under `/var/lib/homelab-recovery`; normal successful runs stay quiet.

## Recovery staging

The builder created a public source archive and copied the selected snapshot into a separate encrypted Restic repository. A complete staged `check --read-data` passed. No plaintext application restore or unlock file was included. The source archive excludes private/runtime files; hashes/sizes identify the artifacts. The builder refused an existing destination without modifying its manifest. A guard also refuses bundle destinations inside the backed-up checkout to prevent recursive backup growth.

The staging role passed preview, actual local temporary-root transfer and hash/tar validation (`changed=2` for copy). A second transfer refused the existing destination. Deliberately corrupting the disposable source archive caused validation to fail and removed only the newly reserved destination. No archive was extracted, no service was deployed and no production directory was used. Staging fixtures and the disposable encrypted repository were removed. A real transfer/provisioning on a separate machine remains untested.

## Local finish and checks

`ansible/finish-vault-work.py` is ready for a user-entered existing Portainer Vault password. It verifies that password before importing anything, creates missing Synapse/adapter encrypted files without overwriting existing ones, and verifies two deployments each for managed Matrix, adapter and Portainer. The second run must be unchanged. A private temporary unlock file is always removed; a credential-free result is recorded locally after success. The user ran the helper locally on 2026-10-21. Its credential-free completion record confirms success at `2026-10-21T10:27:27.628073+00:00`: Matrix reported `ok=51`, adapter `ok=20`, and Portainer `ok=15`, each twice with `changed=0`, `unreachable=0`, `failed=0`. Permanent Synapse/adapter Vault imports and Portainer repeatability are now verified. The temporary unlock file was removed; all 18 subsequent health checks passed. Empty/incorrect-unlock cleanup paths were regression-tested.

All 28 script tests and 17 Ansible tests passed (45 total). All 18 production health checks passed. Outside monitoring and external backup work remain deferred.
