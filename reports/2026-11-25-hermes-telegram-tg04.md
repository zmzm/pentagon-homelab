# TG-04: Hermes Telegram rollout

Task: [TG-04](https://trello.com/c/qSuupRn7), following the
[TG-03 remediation](2026-11-25-hermes-telegram-tg03-fixes.md).

**Deployed alongside Matrix; live acceptance is incomplete.** Telegram polling,
Matrix connectivity, bot delivery, native registration and deployed authorization
checks passed. Human conversation and negative-case acceptance still require
operator evidence. The broader MCP smoke also found a failure in the unchanged
FlowForge inspector. This report does not mark TG-04 complete.

## Authorization and deployment

The operator added the Telegram values privately, then replied “Go ahead and”
to the explicit request to recreate only Hermes, perform limited live
Telegram/Matrix smoke tests and roll back Hermes if needed. No image upgrade,
other-service restart, real restart-tool execution or paid workflow was included.

Repository revision deployed: `b6e478e`. Pre-TG-02 reference: `271d4be`.
Reviewed and deployed Hermes image:
`sha256:2f305c9bdc81731f48664586d23cb6a6f838a15ad7be1bfabe0c3c269d8e09b9`.
Recreation started at **2026-11-25 12:22:35 UTC** using:

```bash
cd apps/hermes
docker compose up -d --no-deps --no-build --pull never --force-recreate hermes
```

Only the Hermes container changed identity. Gateway, broker, approval relay,
planning adapter and inspector retained their container IDs and start times.
The configured image resolved locally to the reviewed image before recreation.
Existing Matrix, gateway and model credentials/settings matched the prior
container. No pull, build, state restore, claim deletion or session reset occurred.
Native skill and memory hashes matched before and after startup.

## Preflight and observed checks

- Private `.env`: mode `0600`, token present, one syntactically valid positive
  numeric user ID. Effective Compose rendering passed without printing secrets.
- Telegram `getMe` and `getWebhookInfo`: authenticated bot, group joining disabled,
  privacy enabled, inline disabled, no webhook, zero pending updates. The bot ID
  was not an authorized human ID. Owning-account two-step verification remains
  the TG-02 operator attestation; it cannot be verified through the Bot API.
- Both native Telegram pairing layouts had no approved/pending files. No native
  Telegram/global authorization keys, legacy `gateway.json` or secondary profiles
  were found. Records were not deleted or migrated.
- Immediate Hermes check: no active agents/work or queued messages. The sole
  cron job was disabled/completed. Gateway had no pending/approved/consumed work;
  four prior requests were DONE. Relay had no pending workflow deliveries and
  retained four historical execution claims. Planning had no RUNNING records.
- Existing local Telegram configuration/policy tests: **7 passed**; verifier
  regression tests: **8 passed** during this task's preparation.
- Deployed runtime state: `matrix`, `telegram` and `api_server` connected, gateway
  running, zero container restart count at the post-recreation check. Telegram
  startup explicitly reported polling mode.
- Native registration verifier: **passed**, including fifteen MCP schemas,
  CLI/Matrix/Telegram/cron selections, prohibited-tool exclusions and curated
  skill listing/prompt-index/view loading. No model request was made by it.
- Deployed authorization probe: **7 assertions passed**. Startup guard loaded;
  listed human in own DM allowed; unknown user, group, mismatched DM and bot
  rejected; unknown-DM behavior ignored. This is a direct native gate check,
  not live traffic from a second Telegram account.
- Real MCP smoke: handshake, schema validation, policy-backed service discovery
  and Vaultwarden inspection passed. The subsequent FlowForge project listing
  failed with `UPSTREAM_FAILED`; the six-tool inspection sequence did not pass.
- Telegram Bot API acknowledged one test message in the allowlisted private
  chat. Matrix acknowledged one test notice in the configured home room after
  an authenticated check confirmed that room was unencrypted. These prove
  provider acceptance, not a human conversation reply or message readership.
- The initial host-side Matrix probe received HTTP 403. Authentication and
  delivery succeeded from inside Hermes using its normal network path.
- Bounded Docker startup logs and up to 64 KiB each of selected native
  gateway/error logs contained no exact configured secret values. This is
  bounded evidence, not a guarantee covering every logging path or historical
  credential. No token, private ID or raw conversation is included here.

## Failures and acceptance limits

The unchanged gateway's direct authenticated inspector `/projects` request
reproduced HTTP 502 `INSPECTION_FAILED` twice. Importing the inspector raised
`ValueError: source code string cannot contain null bytes`. Its
`/app/inspector.py` source contained null bytes and direct source compilation
failed. Bypassing Python bytecode did not resolve the failure. No inspector
repair or restart was performed; this requires separate investigation/rollout.

Hermes startup also reported a config-migration write rejected by the read-only
config mount, an unreadable bundled-skill sync manifest (`UnicodeDecodeError`),
and an invalid native Kanban SQLite database with dispatch paused. The gateway
continued startup and the curated skill checks passed. These observations do
not establish when the file damage originated. Native state and image files
were preserved rather than automatically replaced.

An encrypted Matrix room warning concerned a room other than the configured
unencrypted home room. Encryption behavior was not changed.

Still pending: operator-confirmed authorized Telegram conversation and read-only
tool reply, safe slash-command reply, unauthorized account/group rejection before
model invocation, Matrix conversation regression, and live Matrix approval
routing. The operator was asked to send `/status` and a read-only service-list
request on Telegram and a read-only request mentioning Hermes on Matrix. No
real restart or paid workflow was manufactured to produce an approval prompt.
TG-03's seventeen installed-image rejection tests remain isolated evidence,
not a substitute for these live checks.

## Rollback readiness

A Matrix-only candidate was generated privately in
`/tmp/hermes-tg04-rollout/rollback-compose.yaml`, with
`rollback-config.yaml` mounted read-only. It removes Telegram environment grants,
the Telegram platform/toolset selection and runtime-guard forwarding while
retaining the verified cache tmpfs, `PYTHONPYCACHEPREFIX` and MCP cache forwarding.
Effective Compose rendering and those rollback invariants passed. The candidate
retains the existing image, native home and all other service definitions.

If rollback is needed during this authorized rollout, first repeat the idle-work
check. From repository root, validate and recreate **only Hermes**:

```bash
docker compose --project-directory "$PWD/apps/hermes" \
  --env-file "$PWD/apps/hermes/.env" \
  -f /tmp/hermes-tg04-rollout/rollback-compose.yaml config --quiet
docker compose --project-directory "$PWD/apps/hermes" \
  --env-file "$PWD/apps/hermes/.env" \
  -f /tmp/hermes-tg04-rollout/rollback-compose.yaml \
  up -d --no-deps --no-build --pull never --force-recreate hermes
```

Then verify Matrix connection, native registration and a fresh user-controlled
conversation/approval path. Never restore stale state or start another Telegram
poller. The candidate lives in `/tmp`; regenerate it from the documented
[rollback changes](../apps/hermes/README.md#telegram-alongside-matrix-tg-02)
if absent or if source configuration changes. Reconcile repository configuration
with a rollback before later using its default Compose file to redeploy.

**No live reversal was performed.** The procedure was validated by rendering;
successful rollback and Matrix conversation recovery are not claimed.

Compatibility: native Hermes consumes the Telegram environment/config and guard.
No MCP, gateway, broker or relay API or persisted-record schema changed in TG-04.
Native Telegram sessions/update receipts remain in the existing home on rollback;
existing approval, execution and delivery claims remain owned by their unchanged
services. Normal startup/cache/receipt state may advance; no record replay or
state migration was requested. Private detailed rollout evidence is under
`/tmp/hermes-tg04-rollout` with access restricted to the operator.
