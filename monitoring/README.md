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

### Telegram migration (TG-05, enabled with Matrix retained)

Telegram delivery is **enabled** alongside Matrix as of 2026-11-25 following
operator authorization. Telegram acknowledged the labeled synthetic problem and
recovery messages; a repeated problem sent no duplicate. Recipient observation
of arrival has not been recorded. The existing monitor timer remains active. Keep `notification.type`, its Matrix credentials and `allowed_users`
unchanged until delivery is accepted; Matrix retirement is a separate task.

Use a new notification bot, separate from Hermes. The sender calls only HTTPS
`sendMessage` at `api.telegram.org`, with no inbound listener, webhook, polling,
model invocation or tool/approval access. One positive numeric private-chat ID
is allowed; usernames, groups, channels and migration responses cannot retarget
delivery. HTTP redirects are refused. The token's bot ID must match `bot_id`.

Telegram receives fixed severity/category labels and counts, an original
timestamp and a batch ID. Free-text check details, container/endpoint names,
paths, URLs and provider errors are omitted. Container and endpoint alerts are
grouped; details remain in the local journal and Matrix. Messages use plain
text, disable link previews, request content protection, and remain below 4096
characters. Bot chats do not provide end-to-end encryption.

#### Setup and acceptance (rebuild or replacement bot)

1. Create a **new monitoring bot** in BotFather, disable group joining and inline
   mode, and start its private chat from the intended recipient account. Confirm
   that its bot ID (the token's numeric prefix) differs from Hermes's bot ID.
   Keep the token out of chat, Git, Trello, shell arguments and logs.
2. Create its private credential file, refusing to overwrite an existing file:

   ```bash
   sudo install -d -m 0700 data/monitoring
   sudo python3 -c 'import os; from pathlib import Path; os.umask(0o077); Path("data/monitoring/telegram.env").open("x").write("TELEGRAM_BOT_TOKEN=\n")'
   sudoedit data/monitoring/telegram.env
   ```

   Set `TELEGRAM_BOT_TOKEN=<NEW_NOTIFICATION_BOT_TOKEN>` in the editor. The file
   must be regular, owned by the monitor runner (root for the installed unit)
   and mode 0600. Restore existing credentials from backup when rebuilding.
   Hermes must not receive this credential.
3. Copy `monitoring/config.json` to private
   `data/monitoring/telegram-staged.json` (root-owned, mode 0600). In the
   **staged copy**, set `notification.telegram.enabled` to `true`, `bot_id` to
   the new numeric bot ID as a string, and `chat_id` to the recipient's numeric
   user ID as a string. Keep `credentials_file` as
   `data/monitoring/telegram.env`. Keep delivery disabled during bot replacement.

After authorizing test messages, run these from the repository root using the
same isolated state directory:

```bash
sudo python3 -B scripts/verify_monitor_telegram.py \
  --config data/monitoring/telegram-staged.json \
  --state-dir /var/lib/telegram-test-monitor --phase problem
# Repeat the problem command: it should send no second message.
sudo python3 -B scripts/verify_monitor_telegram.py \
  --config data/monitoring/telegram-staged.json \
  --state-dir /var/lib/telegram-test-monitor --phase recovery
```

Expect one `CRITICAL: TEST delivery` and one `RECOVERED: TEST delivery`, from the
new bot in the intended private chat. Confirm arrival and no sensitive content
in messages or command output. This command collects no real checks, sends no
Matrix events, and uses separate check/reminder state. An empty test queue and
exit 0 establish API acknowledgment; operator observation establishes arrival.
If a test fails, inspect its private retained state before continuing. Do not
reset an ambiguous send to retry it.

After acceptance and rollout authorization, apply the staged Telegram settings
to the deployed `monitoring/config.json`; the timer reads them on its next run,
without a unit restart. On rebuilt hosts install the updated `scheduled_jobs`
role first, including `monitor_telegram.py` and the test command. The tracked
configuration now contains the accepted bot/recipient IDs and enabled setting;
restore the private env credential before enabling the timer on a rebuilt host. Keep Matrix active and verify both channels on the first
real alert/recovery cycle. Offline tests do not establish live acceptance.

#### Delivery state, retries and rollback

The separate root-only `/var/lib/homelab-monitor/telegram.json` (schema 1) holds
Telegram check/reminder history and up to 100 batches. Records bind to the bot
and recipient IDs; changing either requires operator review of the old queue.
Missing state starts a new history. Malformed, unknown or mismatched state stops
Telegram delivery while Matrix continues. A full queue stops advancing Telegram
reminder history and reports failure; eligible queued work still drains. Matrix
and journal alerts continue. This capacity limit can defer or miss a transient
Telegram change during a long outage; consult Matrix for the full history.

Each run sends at most one batch with a ten-second network timeout and 64 KiB
response limit. Confirmed messages leave the queue. Only an explicit Telegram
`ok:false`, error 429 with valid `retry_after` retries automatically: at most
three total attempts, on later timer runs, respecting the server delay and a
minimum exponential delay with jitter. Other explicit client rejections become
`blocked`. Timeouts, redirects, 408/5xx, malformed or wrong-destination responses
become `uncertain`. Both held statuses require review and allow later alerts
through. Pending/held batches cause a nonzero monitor exit and safe journal
counts. Raw provider errors, URLs and tokens are never included in diagnostics.

A `sending` claim is fsynced before dispatch; interrupted claims load as
`uncertain`. A crash after remote success but before confirmation is saved
therefore suppresses replay. Telegram `sendMessage` has no client idempotency
key; local batch IDs cannot guarantee exactly-once delivery. API acknowledgment
does not mean the user read the message. Protocol references:
[sendMessage](https://core.telegram.org/bots/api#sendmessage),
[rate-limit response](https://core.telegram.org/bots/api#responseparameters).

To recover, disable Telegram, let the current monitor finish, and back up its
private state. Inspect the recipient's chat by batch ID/timestamp. Preserve
uncertain evidence; do not change `sending`/`uncertain` to `queued` without an
explicit operator decision about duplicate risk. Correct rejected credentials
or destinations before any manual resend. Never delete state to clear failure.
An intentional bot/recipient replacement needs a separate accepted state history.

Rollback sets `notification.telegram.enabled` to `false`; Matrix continues and
Telegram state is retained. For code rollback restore `monitor.py` and its
configuration together. Old Matrix code ignores the separate Telegram file;
retain it for re-enabling this version. The Matrix status listener still reads
the original notification fields and `status.json`. No gateway, MCP, broker,
relay, FlowForge or native Hermes record changes. Main monitor invocations share
a nonblocking file lock to exclude manual overlap. JSON publication now fsyncs
the file and directory, within host filesystem guarantees; local persistence and
remote delivery remain separate effects.

Initial TG-05 validation on 2026-11-25: 36 monitoring tests, two Matrix status-listener
tests and 17 Ansible tests passed locally. `ansible-playbook scheduled-jobs.yml
--syntax-check` passed with an unrelated installed WinRM plugin warning;
`git diff --check` passed. HTTP boundaries use fixtures: no bot was created,
no Telegram/Matrix messages were sent, and no services were restarted. Telegram
remained disabled pending separate bot setup and live acceptance.

Follow-up on 2026-11-25: a root-owned 0600 `telegram.env` is populated.
`getMe` verified the new bot identity differs from Hermes; `getChat` verified
the intended private recipient is accessible. Inline mode is disabled, but
BotFather still allows group joining: disable it before rollout. A private
`data/monitoring/telegram-staged.json` was prepared. At that stage Telegram
delivery remained disabled and no messages had been sent. Env loading reads one literal
`TELEGRAM_BOT_TOKEN` assignment, optionally single/double quoted, with blank
lines and full-line comments. It never sources the file or expands shell
content; extra/duplicate assignments and files over 4 KiB fail closed. Existing
JSON credential files remain supported when their path is configured, and
Telegram queue schema 1 is unchanged. The monitor is the only changed reader;
Matrix, Hermes, relay, gateway, broker and FlowForge contracts are unchanged.
The updated 38 monitoring tests and two Matrix status-listener tests passed.

Activation on 2026-11-25, explicitly authorized by the operator: the staged
configuration sent one `CRITICAL: TEST delivery` and one `RECOVERED: TEST
delivery` message. Both returned confirmed Telegram API acknowledgments.
Repeating the problem phase made zero send requests, and the isolated test
queue ended empty. Message payloads contained the fixed synthetic label and
no token. The accepted configuration was then applied to the monitor, retaining
Matrix settings. One real `homelab-monitor.service` run succeeded (exit 0): all
18 checks were healthy, Telegram recorded 18 check histories, and both Telegram
and Matrix queues were empty. The existing five-minute timer is active. No
application services were restarted. No real health transition occurred during
this run, so production alert/recovery behavior remains covered by the
synthetic delivery test and offline transition tests. Operator observation
of message arrival remains unrecorded.

BotFather still reports group joining enabled; inline mode is disabled.
Activation proceeded with the sender restricted to the single configured
private chat and no inbound processing. Group joining should still be disabled
in BotFather; the fixed destination is enforced independently of that setting.
Private evidence is retained in ignored
`data/monitoring/telegram-live-evidence.json`; the pre-activation configuration
is backed up as `data/monitoring/telegram-pre-enable-config.json`. Tokens remain
only in the private env file; enabled/bot/recipient settings are tracked.

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

`--check` exits 1 if any check is unhealthy. The scheduled service exits 0 when checks complete and deliveries are acknowledged, even when checks find problems; a nonzero service exit means the checker or delivery needs attention. Matrix failures and explicit Telegram rate limits retain eligible work for later runs; held Telegram outcomes require review. Read the journal or saved check state for health results.

To change thresholds, endpoints, or expected containers, edit `monitoring/config.json`. The next run loads the new config. To change the interval, edit `monitoring/homelab-monitor.timer`, reinstall it, and reload systemd.

## Installation and rebuild

Ansible now manages all three jobs (monitoring, the Matrix status listener, and database backups):

```bash
cd ~/Documents/homelab/ansible
ansible-playbook scheduled-jobs.yml --check --diff
ansible-playbook scheduled-jobs.yml
```

Restore the existing notification credentials and Caddy CA, prepare the host, and start the application containers first. The role installs versioned scripts/configuration, validates and installs all six units, preserves credentials and queued state, and enables their timers. See [Ansible prerequisites and behavior](../ansible/README.md#monitoring-and-database-backup-jobs). The manual unit installation commands below remain useful for troubleshooting; rerunning Ansible reconciles installed units with the tracked sources.

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

Regression tests cover backup health, recovery, reminders, severity escalation, disk thresholds, Matrix retry ordering and stable transactions, encryption refusal, and Telegram projection, destination checks, bounded retries, held uncertainty and crash recovery:

```bash
python3 -B -m unittest discover -s scripts -p 'test_monitor*.py' -v
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

## Weekly recovery verification

`homelab-recovery.timer` runs the isolated file/database/Synapse recovery workflow weekly. The new `backup:recovery` check raises the total to 18: it reports failed verification, a run stuck beyond 35 minutes, and a last successful run older than eight days. Routine success stays quiet; failures and recovery use the existing alert transitions and reminder policy. Status and latest detailed log are root-only under `/var/lib/homelab-recovery`. See [operations](../OPERATIONS.md#scheduled-recovery-verification).

Outside monitoring was deferred by the user on 2026-10-19. No external monitor is active; prepared settings are retained for a future revisit: [setup](EXTERNAL_MONITORING.md).

On 2026-10-21, weekly recovery was extended to test recovered Vaultwarden with a disposable login/encrypted item and recovered Matrix with disposable logins, local messages and authenticated media round-trips. These writes run only inside loopback-only restored copies; original user contents are not decrypted. The installed service passed the expanded workflow. See [the validation report](../reports/2026-10-21-action-batch.md).
