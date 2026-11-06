# Hermes response latency, 2026-11-06

## Incident evidence

The Matrix request asking for current server temperature arrived at
21:10:11 UTC. The final response was ready after 477.8 seconds and the Matrix
adapter confirmed its send at 21:18:09 UTC. Completed GLM-5.3 calls took
169.8, 66.4, 169.4 and 56.9 seconds (462.5 seconds total). Service discovery
and knowledge retrieval took 0.05 and 0.41 seconds. The model first searched
for unavailable shell tools, then described schemas, discovered service
coverage and searched documentation before reporting no host sensor access.
This establishes slow model calls in this turn, not a provider-wide outage.

## Change and compatibility

- Present the small selected tool catalog directly, removing model calls for
  search/description. Tool permissions and selected tools are unchanged.
- In SOUL and the diagnosis skill, stop early for unsupported live host metrics;
  do not substitute documents or Docker health for measurements. Answer delay
  questions from existing evidence instead of starting further investigation.
- Set native Z.ai transport/non-stream stale waits to 60 seconds, gateway
  inactivity warning to 60 seconds and inactivity interruption to 120 seconds.
  Activity resets the watchdog. These are not a total streamed-turn deadline.
  Keep the existing single API attempt and disabled automatic recovery.

Consumers: native provider configuration, model-facing tool assembly and gateway
watchdog. No API/state schema changes, record migrations, approval changes or
session resets. Existing sessions can retain saved prompts and loaded skill
content; fresh user-controlled sessions are needed for prompt acceptance.
Larger initial schema payloads and earlier interruption of slow provider calls
are intentional tradeoffs. Model instructions do not enforce tool permissions.

## Verification and deployment

- Before configuration change, `sudo -n python3 scripts/verify_hermes_skills.py`
  failed the new direct-schema assertion: fifteen personal tools and session
  search were hidden behind discovery. This exercises installed tool assembly
  without model requests; it does not reproduce real GLM latency.
- After change, the same isolated network-disabled check passed for CLI,
  Matrix and cron: direct schemas, prohibited-tool exclusion, native skill
  loading, provider timeout resolution and local diagnostic HTTP guard.
- All 8 `test_verify_hermes_skills.py` tests passed; Compose validation and
  `git diff --check` passed.
- Checked incident completion and no subsequent inbound work in native logs;
  the sole cron job was disabled/completed. Mount hashes matched edited sources.
- Restarted only `personal-agent-hermes-1` to reload existing mounts, avoiding
  recreation against unrelated pending Compose edits. No other service restarted.
  At 21:23:46 UTC the adapter completed initial sync and connected to Matrix;
  the gateway warmed 21 schemas at 21:23:47 UTC.
- Re-ran `verify_hermes_tool_registration.py` in deployed Hermes: all platforms,
  native timeout resolution, allowed tools and exact skill content passed.

No paid model probes, Matrix test messages, session resets or knowledge rebuilds
were performed. Live early-limit replies, watchdog warning delivery and future
GLM latency remain unaccepted. Existing private logs/session records retain the
incident evidence; no chat bodies or credentials are copied here.
