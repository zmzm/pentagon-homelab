# Current improvement actions — 2026-10-21

| # | Action | Current result |
| --- | --- | --- |
| 1 | Manage Synapse configuration | Implemented and adopted unchanged in production. Missing configuration was reconstructed exactly in a private fixture, including supplied encrypted secrets. Permanent Synapse-secret Vault import and both production runs passed with `changed=0`, `failed=0`. |
| 2 | Manage Cloudflare Tunnel routing | Implemented and adopted unchanged; missing configuration was reconstructed from existing credentials and versioned routing. No Cloudflare account or DNS changes. |
| 3 | Extend Vault to the Pi-hole adapter | Import/rendering support passed live authenticated checks using a disposable encrypted Vault; unchanged repeat passed. Permanent user-managed Vault import and both production runs passed with `changed=0`, `failed=0`. |
| 4 | Test Vaultwarden application recovery | Verified from snapshot `4f1f7ed4`: isolated startup/UI, disposable login, encrypted item write/read/sync, database integrity and signing-key preservation. |
| 5 | Expand Matrix recovery checks | Verified from the same snapshot: disposable-account login, unfederated local messages and authenticated media upload/download. Both application workflows now run in weekly recovery verification. |
| 6 | Verify Portainer's permanent Vault repeatability | Completed with the permanent user-managed Vault: both production runs passed (`ok=15`, `changed=0`, `failed=0`). |
| 7 | Prepare replacement-server source and backup staging | Builder and staging role tested with a real encrypted latest-snapshot copy, source archive, checksums, overwrite refusal and corruption cleanup. No separate replacement machine was provisioned. |

## Completion verified

All seven actions are complete within the scope shown above. The user ran `ansible/finish-vault-work.py` successfully on 2026-10-21; the local credential-free completion record confirms success at 12:27 Europe/Warsaw. Managed Matrix, Pi-hole adapter and Portainer each passed twice with `changed=0`, `unreachable=0`, `failed=0`. The temporary unlock file was removed. All 18 subsequent service health checks passed.

Source secrets remain in the plaintext runtime files required by the applications; encrypted Vault files remain Git-ignored. Keep their unlock password separately for recovery.

Outside monitoring and external backup work remain deferred. Existing-user encrypted content, federation, actual separate-host staging/installation, and a complete replacement-machine rebuild remain outside the verification achieved here.

Details: [validation report](reports/2026-10-21-action-batch.md), [managed configuration](ansible/MANAGED_CONFIGURATION.md), [recovery staging](ansible/RECOVERY_STAGING.md).

## Follow-up: replacement-server rehearsal

The [replacement recovery checklist](RECOVERY_CHECKLIST.md) now joins prerequisites, secret/data requirements, staging, deployment order and acceptance checks. It identifies the separate interview application and manual database restore as dependencies. Rehearsal must keep production tunnel, notification and scheduling activity inactive. Execution awaits an identified spare machine or suitable isolated VM; no replacement target has been configured.
