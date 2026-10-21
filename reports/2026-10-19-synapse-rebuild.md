# Isolated Synapse recovery — 2026-10-19

Result: PASS for application startup from local Backrest snapshot `1aac183d`, created at `2026-10-19T17:26:12+02:00`.

Run again with:

```bash
sudo python3 -B scripts/verify-backup.py --matrix-app
```

The verified restore recovered 3406 files/directories (835.404 MiB), with 2979 files content-verified by Restic. Required recovery files were present and the restored Vaultwarden SQLite integrity check passed.

The saved logical PostgreSQL dump was restored in a single transaction into a freshly initialized PostgreSQL 16 instance. The restored Compose password matched the saved Synapse configuration and was used to initialize database authentication. Database checks found 169 public tables, 4 users, 6 rooms, 420 events, and schema version 93.

Synapse started using the restored configuration, signing key and media directory (79 files present). Only the disposable configuration's database host/port, statistics reporting and logging destination were adjusted. Its health and client versions endpoints passed. Its server-key response matched the saved server identity and the public key derived from the restored signing key; the signing-key file remained unchanged.

The test reused the installed image IDs:

- PostgreSQL: `sha256:20edbde7749f822887a1a022ad526fde0a47d6b2be9a8364433605cf65099416`
- Synapse: `sha256:950271eb8700f6a7ca5947a3734164f32110fd31d2f5eef2828bf39a2f05cc21`

PostgreSQL used Docker's `none` network; Synapse shared its network namespace. Container inspection confirmed no published ports, and a check inside Synapse confirmed loopback was the only interface. No production data directory was mounted. Outbound federation, notifications and other external contacts were therefore blocked by network isolation.

Both test containers, anonymous volumes, temporary database storage and restored files were removed. Production Matrix container IDs were unchanged; all 17 production health checks passed before and after the test.

Additional safety fixtures confirmed that a production-directory target is rejected before Docker access and mismatched restored passwords are rejected before container creation or configuration writes. Python syntax and whitespace checks passed.

Limits: this checks application startup and selected read-only APIs, not authenticated login, messaging, media retrieval, federation, replacement-host provisioning, image availability after total host loss, complete repository integrity, or external backup recovery. The external backup destination remains unresolved. Automatic scheduling was not added in this step.

## Scheduled recovery follow-up

Later on 2026-10-19, `homelab-recovery.timer` was installed through Ansible for Sundays 04:30–05:00 Europe/Warsaw, with catch-up after downtime. A real run of the installed service repeated the same snapshot/database/application checks successfully and removed all test resources. A concurrent wrapper run was refused. The next scheduled run was reported as 2026-10-25 04:31:16 CET.

Private atomic status and a single private latest log now live under `/var/lib/homelab-recovery` (directory 0700, files 0600). Monitoring alerts on failed, stuck or overdue verification; routine successes stay quiet. All 18 production checks and all 20 regression tests passed. An unchanged Ansible repeat reported `changed=0`, `failed=0`. See [operations](../OPERATIONS.md#scheduled-recovery-verification).

Independent outside monitoring was prepared using the public Matrix client-versions endpoint and email notification settings, but no external account/monitor has been activated. The endpoint passed a local HTTPS preflight using the explicit monitoring user agent; provider-location checks and notification delivery remain to be verified after account activation. See [external monitoring setup](../monitoring/EXTERNAL_MONITORING.md).

The user subsequently deferred outside monitoring on 2026-10-19. Account creation and activation are no longer active next steps. Weekly recovery verification remains active.
