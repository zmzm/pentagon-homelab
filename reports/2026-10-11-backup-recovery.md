# Backup recovery verification — 2026-10-11

## Results

- Backrest is running. Repository `home-lab` maps `/repos/restic` to `backups/restic` on the host.
- Plan `pentagon-backup` backs up `/userdata/homelab` daily and excludes `/userdata/homelab/backups/restic`.
- Seven daily snapshots are retained. Latest tested snapshot: `879c84b6`, created 2026-10-10 at 17:24:45 +02:00.
- `restic check --read-data` passed: seven snapshots and all 61 packs checked, no errors.
- Full restore into a private temporary directory passed `restic restore --verify`: 2,931 files verified, approximately 950 MiB restored.
- Required Compose, Matrix environment, Synapse configuration/signing key, PostgreSQL version file, Vaultwarden database, Cloudflare Tunnel credentials, and Backrest credentials were present.
- Restored Vaultwarden SQLite database passed `PRAGMA integrity_check`.
- The temporary restored copy was removed. Production service data was never a restore target.

## Remaining gaps

1. The verified repository is local and shares the server's root storage device (`mmcblk0p2`). A separate encrypted USB repository was initialized under `homelab-backups/restic` on the PNY exFAT drive (UUID `E31C-6360`), but the first copy encountered repeated USB resets and write I/O errors. The copy was interrupted. The USB repository is incomplete and unverified; it must not be relied on for recovery. Existing personal files were not intentionally modified. No formatting or filesystem repair was performed.
2. Resolved in the database follow-up below: hourly consistent PostgreSQL dumps are configured and recovery from a new Backrest snapshot was verified. Raw live database files alone are still not a verified recovery source. Full Synapse application startup remains untested.
3. A complete application rebuild and external-destination restore have not been tested.
4. Repository password and recovery instructions must be available outside the server. The password exists in Backrest's local configuration; restoring that configuration requires access to the encrypted repository first.
5. This snapshot predates today's TURN and Netdata cleanup. Do not restore retired services into production accidentally.

## Repeat the file restore test

From the repository root:

```bash
sudo python3 scripts/verify-backup.py
```

This uses the configured local repository, restores the newest snapshot tagged `plan:pentagon-backup` into a private directory under `/tmp`, verifies restored file contents, checks critical recovery files and Vaultwarden SQLite integrity, and deletes the temporary copy. It needs roughly the snapshot's uncompressed size plus 512 MiB of free space in `/tmp`. It does not run the full repository integrity check, start PostgreSQL, or test an external backup.

Restic references: [restore verification](https://restic.readthedocs.io/en/stable/050_restore.html), [repository integrity checks](https://restic.readthedocs.io/en/stable/045_working_with_repos.html#checking-integrity-and-consistency).

## USB copy failure

The first run of `sudo env PYTHONDONTWRITEBYTECODE=1 python3 scripts/backup_usb.py --initialize --verify` successfully initialized the encrypted repository, then failed during the first snapshot copy. Kernel logs showed repeated `reset SuperSpeed USB device`, `I/O error, dev sda` on writes, and `device offline or changed`. Restic reported `input/output error` while synchronizing pack files. `vcgencmd get_throttled` returned `0x0`; the root cause remains unconfirmed. A stop signal was sent to the copy process.

Next diagnostic step: try another USB port, then inspect the connection and incomplete repository before retrying. No automatic USB copy schedule is installed. Full USB integrity and restore tests remain pending. The local repository is unchanged.

## Reconnection and filesystem check

The drive was reconnected on USB path `1-1` at high speed (USB 2), replacing the original SuperSpeed path `4-1`. A check while unmounted, `fsck.exfat -n /dev/disk/by-uuid/E31C-6360`, exited 4 and reported corrupt directory-entry checksums and unknown entries under `homelab-backups/restic`; eight files were reported corrupt, zero fixed. No filesystem repairs were made and the backup copy was not retried. A private local safety archive of the existing files (excluding the incomplete backup folder) was created at `data/usb-recovery/2026-10-11/original-files.tar`: 95 files, 203,622,400 archive bytes. The source was mounted read-only; the archive checksum and readability were verified. No new USB I/O errors were observed during the safety copy. The drive was then unmounted. Filesystem repair requires user approval because it can remove damaged entries.

## Approved repair

The user approved filesystem repair and recreation of only the backup folder. `fsck.exfat -p` fixed eight damaged entries; the subsequent read-only `fsck.exfat -n` exited 0 and reported a clean filesystem. The repaired drive was mounted with `nosuid,nodev`. Comparison found 94 existing files matching the safety archive. One approximately 200 MB file in hidden `.Trashes` had different contents despite unchanged size and timestamp; two repeated reads produced the same current hash. Its current version was preserved separately at `data/usb-recovery/2026-10-11/trash-item-after-repair.bin`, while the pre-repair version remains in the original safety archive. Only the incomplete `homelab-backups` folder was removed and recreated.

## Retry failed after repair

The encrypted repository was recreated and copying retried on USB 2. During writes, the kernel reported `usb 1-1: USB disconnect`, followed by device-offline and buffer I/O errors. Restic reported `no such device` and `input/output error`. The copy was interrupted and the stale USB mount removed. No completed, verified external backup was produced. `vcgencmd get_throttled` again returned `0x0`. The USB device/connection remains unreliable; use a different destination before relying on an external backup. No automatic USB backup schedule is installed.

## Authorized format attempt

The user authorized formatting the USB drive and retrying. Before formatting, the local safety archive checksum and its 95-file inventory were verified; the separate post-repair trash-item copy was also confirmed present. The target was checked against the recorded USB serial, capacity 62,914,560,000 bytes, and the single `/dev/sda1` partition. The drive was unmounted, then `mkfs.ext4 -F -m 0 -L homelab-backup -E nodiscard` was started. It printed a candidate filesystem UUID but stalled during filesystem creation while the kernel repeatedly reset USB path `2-1`. A termination signal was sent. Formatting has not been verified as complete; the drive's previous contents must be treated as erased. No backup retry was started. The saved safety copies and local encrypted backup remain on the server.

## Format retry on another USB 2 port

After the user changed ports, the recorded serial was detected on USB path `1-2`; the prior formatter had exited and no recognizable filesystem was present. The authorized ext4 format was retried against the identity-checked partition. The kernel again reported `reset high-speed USB device` during formatting. The formatter was marked for termination. A usable filesystem and external backup remain unverified. Further retries on this drive are not configured; the local safety archives remain preserved.

## Consistent Matrix database backup and recovery follow-up

- Installed `homelab-matrix-backup.timer`: hourly custom-format `pg_dump`, plus boot catch-up. The latest complete dump is published atomically at `data/matrix/database-backup/synapse.dump`, mode 0600 in a 0700 directory; failures preserve the previous good dump.
- Monitoring now checks dump freshness (critical after two hours), presence, size, and invalid future timestamps. There are 17 production checks.
- The current PostgreSQL 16.13 database was about 20 MB. Direct isolated restore passed.
- Backrest plan `pentagon-backup` completed successfully as operation 1026, creating snapshot `69ce6af6` at 2026-10-11 18:57:46 +02:00. Its existing included path contains the new dump; no Backrest credentials or schedule were changed.
- `sudo python3 -B scripts/verify-backup.py --matrix-db` restored 835.413 MiB into private temporary storage and verified 2,849 files. Required recovery files were present; Vaultwarden SQLite integrity passed.
- The dump recovered from that snapshot restored successfully in a separate PostgreSQL container using `pg_restore --single-transaction`. Schema/data queries found 169 tables, 4 users, 6 rooms, 401 events, and Synapse schema version 93.
- The test container had no network or production mounts. The container, its temporary database storage, and restored files were removed. Production Synapse and PostgreSQL were not stopped or restored into.
- Regression tests verify failed dumps/invalid archive indexes preserve the last good copy, published dump permissions are private, and missing/empty/stale/future dump files produce monitoring alerts.

This closes the consistent database backup/recovery gap. It does not establish external/off-site backup protection, point-in-time recovery, or a full Synapse application rebuild. Hourly dumps are captured by daily Backrest snapshots; both remain on the same server storage until external replication is configured. See [database backup operations](../OPERATIONS.md#matrix-database-backups).
