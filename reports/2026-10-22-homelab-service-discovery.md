# Policy-backed service discovery: deployment and verification

On 2026-10-22, the user authorized deployment of the new read-only
`homelab_list_services` operation. Verification completed at 19:09 UTC
(21:09 Europe/Warsaw). The implementation was subsequently committed and pushed
as `f1d7695` (`Add policy-backed homelab service discovery`). Deployment used
the same checkout before that commit; deployed gateway source hashes matched
the checkout and the loaded curated skill matched its repository content.

## Behavior and boundaries

The existing MCP bridge calls authenticated GET `/homelab/services`. The gateway
reads its loaded `policy.services` and returns only service identifiers and
restart levels, labelled `configured_tool_coverage`. The inventory includes
configured services with DENY restart permission and supports an empty policy.
It makes no broker or Docker request and exposes no container configuration,
secrets, host paths or environment variables. Coverage is not evidence of
running state, health or reachability. Restart permissions are informational;
existing authorization and confirmation checks remain authoritative.

CLI, Matrix and cron select the tool through the existing personal MCP group.
The diagnosis skill discovers identifiers when unknown or coverage is needed,
without a hardcoded service list. Genuinely ambiguous targets require a user
choice; discovering one plausible configured target cannot authorize choosing it.

## Checks performed

| Check | Result |
| --- | --- |
| Gateway suite | All 39 tests passed, including policy-only discovery without a broker backend, authentication, audit context, exact output fields and unchanged DENY/CONFIRM restart behavior. |
| MCP bridge fixtures | All 3 tests passed: actual SDK registration/schema, authenticated GET with audit annotations, and preservation of authentication failure. |
| Diagnosis validation fixtures | All 8 tests passed, including deferred tool calls, discovery without target selection, unanswered clarification and validation HTTP guard exclusions. |
| Offline installed-image validation | Passed native registration of nine personal tools, effective CLI/Matrix/cron selections, prohibited-tool exclusion, native skill discovery/loading and guarded read-only request fixtures. No model request or Matrix adapter was started in the disposable container. |
| Deployed native registration | Passed nine-tool inventory, effective CLI/Matrix/cron selections and exact curated skill loading through Hermes' filtered subprocess environment. |
| Deployed MCP smoke check | Passed real MCP handshake, policy coverage response field checks and the existing read-only Vaultwarden inspection. |
| Deployment isolation | Only gateway and Hermes were recreated. Every other container retained its ID, start time and running state; the policy checksum was unchanged. |

Compose validation and whitespace checks also passed. The homelab knowledge
snapshot was refreshed and checked before deployment. It contained ten selected
documents, recorded the pre-commit revision and dirty documentation accurately,
and was ready, not stale, with no detected source changes at that check.
Documentation commits require a subsequent refresh to record the committed
revision; this does not require a service restart.

## Rollout

The offline native check ran first, followed by the documentation refresh and
Compose validation. Only `flowforge-gateway` was built. Its container was
recreated with `--no-deps --wait --wait-timeout 60`; its health check passed
before Hermes was recreated with `--no-deps --force-recreate`. Both containers
were running at final verification, and the gateway remained healthy.

No broker, Matrix infrastructure or inventoried application was restarted.
Service permissions and credentials were unchanged. Verification requested no
restart or approval and made no model request or operator-authored Matrix test
message. No live discovery dialogue was exercised.

## Limits and follow-up

Native registration and read-only MCP success verify the deployed tool path.
They do not establish that the model will choose discovery correctly in a real
conversation. The discovery-specific live GLM and end-to-end Matrix behavioral
cases remain untested; cron verification covers effective tool selection only.
Earlier accepted CLI/Matrix diagnosis behavior predates this discovery update.
Use a fresh user-controlled session for later behavioral acceptance because
saved conversations can retain older instructions and loaded skill content.

See [the API and repeatable rollout procedure](../apps/hermes/README.md#service-discovery-and-rollout)
and [the operations guide](../OPERATIONS.md#personal-agent-discovery-and-diagnosis).
This record omits credentials, private message/event/session identifiers,
memory contents and raw service logs. Private detailed evidence remains local.
