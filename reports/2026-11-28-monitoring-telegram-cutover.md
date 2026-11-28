# Telegram-only server alert setup — 2026-11-28

The operator authorized setup after populating the private monitoring bot variables.
The monitoring bot authenticated with Telegram, group joining was disabled, and
`getChat` confirmed the configured destination is a private chat. No credentials
or destination identifiers were printed or committed.

## Configuration and compatibility

`monitoring/config.json` selects `notification.type: journal` and retains enabled
Telegram delivery. The existing monitor supports this combination: detailed local
journal entries and Telegram category/count summaries, without Matrix credential
reads or sends. The old Matrix credential/user fields remain for rollback and
legacy readers. Matrix pending records are retained without dispatch; Telegram
schema-1 state and its bot/recipient binding, bounded retries and uncertain-send
claims are unchanged. The SmallTV exporter retains its existing health-state input.

The scheduled-jobs role now accepts Telegram-only configuration, validates the
private Telegram credential file, and omits/disables the Matrix status timer.
Full-role database/backup/recovery prerequisites remain unchanged. The host rollout
installed only monitoring units, without running the full scheduled-jobs playbook.
No backup/recovery job or application was installed, started or restarted.
Telegram has no status command listener; use `monitor.py --check` for current details.

## Verification and deployment

- 47 monitoring tests and two Matrix status tests passed. The added regression
  covers Telegram alert/recovery and duplicate suppression in journal mode without
  Matrix credentials, preserving existing Matrix queue records.
- 17 Ansible tests passed; scheduled-jobs syntax check and `git diff --check` passed.
- `systemd-analyze verify` passed for the monitor service and timer.
- The isolated `/var/lib/telegram-test-setup-20261128` synthetic problem, repeated
  problem and recovery sequence returned success with empty queues. Telegram
  acknowledged the problem/recovery messages. Recipient observation is unrecorded.
- Installed `homelab-monitor.service` and `.timer` from tracked definitions;
  daemon-reloaded, started the monitor and enabled the timer at boot. The timer is
  active, with the next run observed at 10:13:07 CET. The immediate timer invocation
  after the manual first run produced zero alert changes/reminders.
- The real monitor run succeeded, with 18 check histories, six problems, zero
  pending Telegram batches, zero held sends and zero retained Matrix batches.
  Telegram acknowledged the first real alert batch. No Matrix status units were
  installed on this host.

## Observed health issues

Homepage, Matrix Synapse and Matrix PostgreSQL containers were absent. Matrix HTTP
health failed, its database dump was missing/empty, and no scheduled recovery
verification result existed. These are retained coverage findings, not delivery
failures. No service was removed from checks to hide them; deciding whether to
restore or retire those services/jobs is separate work.
