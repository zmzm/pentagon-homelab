# Lightweight server monitoring

`homelab-monitor.timer` runs `scripts/monitor.py` every five minutes. The process exits after each run; there is no metrics agent or dashboard. Configuration is in `monitoring/config.json`.

## Coverage

- Root filesystem: warning at 85% used; critical at 95% used or less than 2 GiB free.
- Twelve containers managed by this repository: missing, stopped, unhealthy, or still starting at check time are reported. Containers without Docker health checks are checked for running status only.
- Matrix: local Synapse `/health` must return `OK`.
- Vaultwarden: `/alive` through local Caddy, verifying TLS against Caddy's local CA.
- Matrix database dump: missing/empty files, timestamps more than five minutes in the future, or age over two hours are critical. The hourly dump timer and recovery tests are documented in [database backup operations](../OPERATIONS.md#matrix-database-backups).
- Backrest: latest completed real backup must succeed, and the newest successful backup must be no more than 36 hours old. Warnings are reported separately. Future scheduled runs and dry runs do not count as successful backups. History is read through Backrest's operations API on its private Docker address.

The checks cover the repository's containers, not unrelated application projects on this host. They do not prove database recoverability, backup repository integrity, DNS correctness, or public Matrix/Cloudflare availability. A stopped host cannot report its own outage; external monitoring would be needed for that.

## Alert delivery

Delivery is active in the private **Server alerts** Matrix room, without end-to-end encryption as requested. The existing `@homelab:pentagonlab.org` bot invited `@vladjik:pentagonlab.org`. Accept the invitation in Matrix. The FlowForge control room and its configuration were left unchanged.

The bot token and room ID are stored in ignored `data/monitoring/matrix.json`, readable only by root (0600, directory 0700). The monitor uses the local Synapse API at `http://127.0.0.1:8008`; no public IP, new domain, or inbound port is required. Revoking the shared bot token also affects monitoring; replace the token in this file after rotation. Never commit or paste this file into logs.

Matrix messages use colored status labels: 🚨 red for critical issues, ⚠️ amber for warnings, and ✅ green for recovery. Issue icons identify 💾 disk, 🗄️ backups, 🐳 containers/Docker, 💬 Matrix, 🔐 Vaultwarden, and 🌐 other endpoints. Colors use Matrix HTML formatting; clients that omit colors still show the emojis and status text. Message content is HTML-escaped. A single clearly labeled preview was sent to the alerts room to demonstrate the styles.

Formatting reference: [Matrix message HTML](https://spec.matrix.org/v1.16/client-server-api/#mroommessage-msgtypes).

Alerts remain in the journal too. A durable queue in the saved state retries failed Matrix deliveries every five minutes, oldest first, using stable transaction IDs to avoid duplicates after an ambiguous timeout. Original timestamps identify delayed alerts. If the room enables encryption later, plaintext delivery stops and messages remain queued; create a new unencrypted room and update the room ID. A Matrix outage can only be delivered after Matrix recovers; complete host failure still needs external monitoring.

A problem produces a message on first detection or severity change. Unchanged problems repeat after six hours. Recovery produces a `RECOVERED` message. Alert state persists in `/var/lib/homelab-monitor/state.json`, mode 0600; it survives reboots. Each run also logs a check summary.

Backrest currently has authentication disabled. If authentication is enabled or the API changes, its check will report an error until the monitor is updated. Check details deliberately omit API response bodies and raw exceptions to avoid logging secrets.

## Matrix status command

Send **`!status`** in **Server alerts**. `status` and `/status` are also accepted when the client sends them as message text. The listener polls every 15 seconds, so replies normally arrive within 15–30 seconds. Only `@vladjik:pentagonlab.org` is authorized, through `notification.allowed_users` in `monitoring/config.json`. Other rooms, senders, edited messages, and unrelated text are ignored. Initial startup skips historical commands.

Each request runs fresh checks and replies with a timestamp, healthy check count, disk usage/free space, container status, Matrix/Vaultwarden health, and backup age/result. Healthy entries use ✅ green. This does not alter scheduled alert state or reminders. Replies retain the private room's lack of encryption.

`homelab-matrix-status.timer` runs the short-lived `scripts/matrix_status.py`; it has no resident process. Its cursor and retry queue live in `/var/lib/homelab-monitor/status.json`. Failed replies retry with stable transaction IDs. The listener uses a separate sync cursor and only the alerts room, leaving FlowForge's control room unchanged. If more than 100 matching messages arrive between polls, Matrix may truncate the timeline; send the command again if no reply arrives.

```bash
sudo journalctl -u homelab-matrix-status.service --since today
systemctl list-timers homelab-matrix-status.timer
sudo systemctl disable --now homelab-matrix-status.timer
```

Reinstall/rebuild the listener with:

```bash
sudo systemd-analyze verify monitoring/homelab-matrix-status.service monitoring/homelab-matrix-status.timer
sudo install -m 0644 monitoring/homelab-matrix-status.service monitoring/homelab-matrix-status.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-matrix-status.timer
```

Command authorization and startup/history behavior have two regression tests:

```bash
python3 -B -m unittest discover -s scripts -p test_matrix_status.py -v
```

Protocol reference: [Matrix sync API](https://spec.matrix.org/v1.16/client-server-api/#get_matrixclientv3sync).

## Commands

From the repository root:

```bash
# Inspect all current checks without altering alert state:
sudo python3 -B scripts/monitor.py --check

# View alerts and summaries:
sudo journalctl -u homelab-monitor.service --since today

# See the next scheduled run:
systemctl list-timers homelab-monitor.timer

# Run immediately using production state:
sudo systemctl start homelab-monitor.service

# Stop scheduled checks:
sudo systemctl disable --now homelab-monitor.timer
```

`--check` exits 1 if any check is unhealthy. The scheduled service exits 0 when checks complete, even when they find problems; a nonzero service exit means the checker or Matrix delivery failed. Delivery failures leave queued alerts for the next run. Read the journal or saved check state for health results.

To change thresholds, endpoints, or expected containers, edit `monitoring/config.json`. The next run loads the new config. To change the interval, edit `monitoring/homelab-monitor.timer`, reinstall it, and reload systemd.

## Installation and rebuild

The initial installation is active as of 2026-10-11. Units are copied into `/etc/systemd/system`; the source copies in this directory are tracked. Reinstall after changing units:

```bash
sudo systemd-analyze verify monitoring/homelab-monitor.service monitoring/homelab-monitor.timer
sudo install -m 0644 monitoring/homelab-monitor.service monitoring/homelab-monitor.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-monitor.timer
sudo systemctl start homelab-monitor.service
```

The unit runs as root to access Docker and Caddy's CA files. It uses a read-only filesystem view with a dedicated writable state directory, private temporary storage, and a 90-second timeout. Paths in the unit match the current repository location; update them when rebuilding elsewhere.

## Validation

Thirteen regression tests cover failed backups followed by future schedules, dry runs, stale backups, recovery, deduplication, reminders, severity escalation, low free space, delivery retry ordering, stable transaction IDs, refusing plaintext in encrypted rooms, and missing/empty/stale/future database dumps:

```bash
python3 -B -m unittest discover -s scripts -p test_monitor.py -v
```

The live first run passed all 16 checks. A separate configuration and state directory verified a closed local port produces an alert, a repeated failure does not duplicate it, and restoring the real URL produces a recovery message. No production services were stopped. The first scheduled check used about 0.21 seconds of CPU time; idle monitoring has no resident process.

Backrest references: [operations API](https://garethgeorge.github.io/backrest/docs/api), [operation statuses](https://github.com/garethgeorge/backrest/blob/main/proto/v1/operations.proto).

Matrix delivery was verified with a welcome message, an isolated test alert, and a recovery message on 2026-10-11. A repeated test failure produced no duplicate alert; all 16 production checks remained healthy. No production services were stopped.

To recreate the room after rebuilding (only when the credential file does not already exist):

```bash
sudo python3 -B scripts/setup_matrix_alerts.py \
  --bot-env /home/pentagon-admin/Documents/apps/matrix-flowforge-bot/.env \
  --recipient @vladjik:pentagonlab.org --bot-user @homelab:pentagonlab.org
```

This uses the existing bot token, checks its account, creates an invite-only room without encryption, and saves its credentials privately. Restore `data/monitoring/matrix.json` from backup to retain the existing room instead.

The database follow-up adds a seventeenth production check. The hourly dump script has two additional tests for keeping the last good dump on failure and publishing a private complete file: `python3 -B -m unittest discover -s scripts -p test_backup_matrix_db.py -v`.
