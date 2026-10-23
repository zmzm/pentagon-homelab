# FlowForge planning attachments: deployment and verification

On 2026-10-23, the user authorized documentation updates and deployment of the
completed Matrix delivery change. Implementation commit `11ef38a` was already
pushed to `origin/main`. The relay was recreated at 11:20:40 UTC (13:20:40
Europe/Warsaw); runtime verification completed at 11:23:11 UTC.

## Behavior and boundaries

Completed runs produce one deterministic English completion notice containing
the task ID, run ID, outcome and available plan filenames, followed by complete
UTF-8 `concept-plan.md` and `grounded-plan.md` attachments. Only the authenticated
gateway's sanitized workflow response enters delivery; no raw FlowForge files
are attached and no additional model summarizes the plans. Failed-run notices
contain a short error code rather than plan contents or tracebacks.

The existing Matrix account, room, credentials and state volume were preserved.
Durable delivery state records full sanitized plans, upload claims, media URIs
and message acknowledgments. Message retries reuse the same transaction and
content. Uncertain media uploads are held for review; explicit rate-limit
rejections have a bounded retry budget. Incomplete delivery retains a failure
record and a bounded fallback, with complete available sanitized plans retained
in state. Approval decisions and execution claims retain their existing meaning.

## Checks performed

| Check | Result |
| --- | --- |
| Implementation test suite | All 81 gateway tests passed before the implementation commit, including complete attachment contents, partial delivery failures, restart/retry behavior, approval boundaries and gateway redaction. |
| Existing Python fixtures | All 7 FlowForge adapter, 3 Hermes MCP bridge and 8 skill-verification tests passed; no real planning execution. |
| Built relay image | All 26 approval and delivery tests passed in a disposable container with no external network, production credentials or production state. The tests used local fake Matrix/gateway HTTP servers. |
| Compose | Configuration validation and targeted recreation with `--no-deps --wait --wait-timeout 60` passed. |
| Deployed source | All eight deployed `.mjs` source hashes matched the implementation checkout. |
| Matrix access | Read-only requests authenticated the existing account, read the configured unencrypted room and confirmed a 52,428,800-byte media limit. No media was uploaded and no event was sent. |
| Gateway access | Health request succeeded; the relay's existing approver credential was accepted. The gateway remained healthy. |
| Durable state | The same four prompt records were retained unchanged. There were no pending workflow deliveries or unfinished decisions before rollout. The new process persisted polling state after restart and retained its sync cursor. |
| Runtime | Relay running with restart count zero and no relay failure log events during verification. Compose reports running readiness; the relay has no dedicated health check. |
| Isolation | All 23 other containers retained their IDs, image IDs, start times, running states and restart counts. All container environments and mount sets, plus the service-policy checksum, were unchanged. |

The deployed relay image is
`sha256:b04449d29baf2e1622bfc49462ac4902f522ae1f3946d33612a88bee430cab42`.
Private baseline metadata and a mode-0600 relay-state backup were retained in a
mode-0700 local rollout directory. This public record contains no credentials,
task/plan contents or Matrix event/session identifiers.

## Rollout and recovery

Only `matrix-approvals` required a new image and container. Hermes, the gateway,
the FlowForge planning API, the broker and Matrix infrastructure did not require
recreation. The documentation was updated across the component guides, service
inventory, architecture, operations and root README. The allowlisted homelab
knowledge projection is refreshed and checked after documentation changes;
refresh after the documentation commit records the committed revision without
restarting services.

See [repeatable deployment and delivery recovery](../apps/hermes/README.md#planning-result-delivery).
Preserve the current relay state when rolling back code: a stale pre-deployment
state backup can lose delivery progress. An older relay does not understand the
new per-file delivery records; review any pending/failed deliveries before using
it, and never clear an uncertain upload claim or repeat planning blindly.

## Validation limits

No paid planning run, model request, real service restart through an approval,
operator-authored Matrix test message or live attachment upload was used for
validation. The earlier live planning acceptance verified the former text
delivery path. Complete attachment delivery and recovery behavior are verified
by isolated fixtures; a future user-approved completed run will exercise the
live attachment path. The read-only runtime checks establish connectivity,
authorization and configuration, not live end-to-end media delivery.
