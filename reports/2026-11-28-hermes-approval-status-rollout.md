# Hermes approval status rollout

Deployment completed on 2026-11-28; final verification at 11:47 UTC.
Implementation: `89097a2` (read-only approval decisions and execution outcomes).
The user explicitly authorized gateway deployment and a Hermes reload.

## Preflight and deployment

- Clean working tree and valid `docker compose config --quiet`.
- Gateway retained two DONE approvals, with no PENDING, APPROVED or CONSUMED
  records. Relay planning delivery was complete; adapter records had no RUNNING
  jobs. Hermes' live `active-work` control query reported zero active agents and
  an empty work list; its saved agent count had been stale.
- Built only `pentagon-gateway`, recreated it with `--no-deps`, and waited for
  its health check. New image ID:
  `sha256:4716e5e9adcb9a08384636f74b58aaca9ebdf928873bc8281d30c8014d875c52`.
- Recreated only Hermes with `--no-deps --force-recreate --pull never` to reload
  the bridge, include list and SOUL. Existing native state and credentials were
  retained; no session reset, approval creation or execution was performed.
- Broker, Telegram approval relay, FlowForge adapter and inspector container IDs
  remained unchanged.

## Observed verification

- Gateway healthy. Its deployed status route read both retained terminal
  approvals with the gateway credential, matched their statuses, omitted raw
  decision/context fields, and left approval file bytes unchanged.
- Deployed native registration passed: sixteen personal MCP tools, including
  `approval_get_status`, selected for CLI, Telegram and cron. Native skill loading
  and prohibited-tool checks passed.
- Read-only deployed MCP smoke passed: handshake, catalog/schema, service coverage,
  Vaultwarden inspection (running), and all six FlowForge inspection contracts.
  These reads append gateway audit evidence; they do not execute repairs.
- Hermes runtime reported `gateway_state: running`, session store `ok`, and
  Telegram `connected`. Startup logs confirmed polling-mode connection after a
  DNS-over-HTTPS fallback.

## Limits

No model call, human approval/rejection event, restart test, paid planning run or
Telegram test message was sent. This verifies deployed registration and read paths,
not live conversational acceptance. Hermes checks approval status on follow-up;
the separate approval bot does not automatically wake its conversation. Existing
saved session prompts can retain older guidance; a fresh user-controlled session
is appropriate for accepting the new behavior.

The container runtime warned that host memory limits are unsupported. Hermes
startup also logged configuration-migration and dependency/plugin warnings; the
read-only configuration mount was preserved and final readiness checks passed.
No image upgrade or permission widening was performed to address these warnings.
The homelab knowledge snapshot was not refreshed or rebuilt during this rollout.
