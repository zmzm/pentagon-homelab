# Telegram private status command — 2026-11-28

The operator requested the former Matrix `!status` functionality, including a
service list, memory and status, and a command-menu button. The checked-in Matrix
listener already reported configured checks, disk, endpoints and backups; it did
not report RAM. Telegram now adds RAM from `/proc/meminfo` (total minus available).

## Implementation and contracts

`telegram_status.py` implements fresh `/status`, `!status` and `status` requests.
Authorization requires the configured private recipient as both sender and chat,
a human sender and an original message no more than ten minutes old. Edited,
forwarded, bot, group and unknown-user messages are ignored. The handler never
passes message text into a shell, model, gateway or arbitrary tool. Health checks
reuse `monitor.collect`; only configured services are reported. Running-only
containers are not claimed application-healthy. Output is escaped, bounded and
explicitly marks omitted rows. Memory failure is reported as unavailable.

A chat-scoped `/status` command and commands menu button are registered and read
back for verification. The short-lived systemd listener polls every 15 seconds;
its first poll skips historical updates. Only this listener polls the separate
monitoring bot. Hermes and approval bot identities were checked for separation.
No webhook is deleted automatically. Menu configuration is available through
`--configure-menu` and integrated into scheduled-jobs Ansible deployment.

The new root-only `telegram-status.json` is schema 1, with bot/chat binding,
update cursor and frozen replies. Its local lock, incoming cursor and reply
queue are separate from monitor reminders, alert delivery and Matrix records.
Commands arriving in one poll share a fresh report. Cursor and reply intent are
persisted together before dispatch; a durable sending claim prevents automatic
replay after ambiguity or a crash. Only explicit 429 rejection retries, with
bounded delay and three total attempts. At most 100 held/pending reports are
retained; a full queue drains eligible replies without advancing the cursor.
Unknown versions or changed identity fail closed. No retained record is migrated
or discarded. The status report deliberately includes service/check details in
the authorized private chat; automatic Telegram alerts keep category summaries.
No token, raw provider error, host log or model content is sent in the report.

Consumers affected: the monitoring bot's private command menu and incoming
updates, the new systemd listener and state reader, and scheduled-jobs Ansible
timer selection. Existing monitoring/Matrix/SmallTV/Hermes/gateway state formats
are unchanged. Ansible retains legacy Matrix selection and stops the Telegram
timer when Telegram is disabled. For manual rollback disable the Telegram
status timer while retaining its state; automatic alerts remain independent.

## Verification and live acceptance

- 11 status tests passed: authorization/forwarding/edit rejection, RAM, bounded
  escaped output, bootstrap/cursor deduplication, persisted claims, ambiguity,
  confirmation-save failure, bounded rate-limit retries, malformed/versioned
  state, webhook refusal, full-queue draining, menu scope and safe errors.
- 47 monitoring, two Matrix status and 17 Ansible tests passed.
- Scheduled-jobs syntax check and local Ansible assertions for Telegram-only and
  legacy Matrix timer selection passed. `git diff --check` passed.
- systemd unit verification passed. Installed and enabled only the new status
  service/timer, daemon-reloaded and ran the bootstrap. Both monitoring timers
  were active; no application/backup/recovery service was restarted.
- Telegram acknowledged menu changes; command list and button type were read back.
- At 10:15:34 CET the listener processed one real command, finishing successfully
  with zero pending/held replies. Subsequent polls processed zero commands,
  showing no replay of that update. The operator replied **worked** to the
  request to test Menu → `/status` and confirm service/RAM content. This is live
  acceptance of the private menu and reply, not of negative-user scenarios.
