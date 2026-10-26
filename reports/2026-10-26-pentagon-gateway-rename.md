# Pentagon Gateway rename — 2026-10-26

The Hermes tool gateway was renamed from `flowforge-gateway` to
`pentagon-gateway` and deployed on the Pentagon host. FlowForge remains the
separate task runner.

## Changes

- Renamed `apps/flowforge-gateway` to `apps/pentagon-gateway`, including its private npm package.
- Updated Compose service, build contexts, dependencies, policy mounts and internal gateway URLs.
- Moved `data/flowforge-gateway` to `data/pentagon-gateway` while the gateway was stopped. All 13 retained files were identical immediately after the move; approval records remained identical after startup. Read-only verification added normal audit events.
- Updated the MCP bridge default URL, Hermes identity instructions, projection-builder imports, policy fixture path, architecture/services documentation, repository instructions and engineering guide.
- Added cutover and rollback instructions to the Hermes guide. Historical deployment evidence retains its original service name with a link to the current name.
- Rebuilt the gateway and Matrix approval relay; recreated the broker for its relocated policy mount and Hermes/relay for the new URL. Removed the stopped old gateway container after verification.
- Refreshed the homelab documentation projection; its freshness/source check passed. It records uncommitted documentation changes accurately.

Existing uncommitted changes were preserved. The FlowForge task runner, planning
API, credentials, policy contents, HTTP/MCP contracts and stored record formats
were retained.

## Verification

- 145 gateway tests passed, including real local Knowledge Router integration.
- Four MCP bridge fixture tests passed offline in the installed Hermes image.
- Eight skill-verification tests passed.
- Compose configuration validation and image builds passed.
- Pentagon Gateway is running and healthy; Hermes, the broker and relay are running.
- Both deployed callers use `http://pentagon-gateway:8080`; gateway state and policy mounts use the new paths.
- Native Hermes registration verified all nine personal tools and effective CLI, Matrix and cron selections.
- Real MCP handshake, policy-backed service discovery and read-only Vaultwarden inspection passed.
- Git whitespace validation passed.

The host Python environment lacks Pydantic, so bridge tests used the installed
Hermes image. Local fixture-socket tests used the approved execution environment.
No paid planning run or live Matrix approval/attachment exchange was performed.
The changes remain uncommitted.
