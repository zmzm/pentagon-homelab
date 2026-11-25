# TG-03 remediation

Follow-up to the [security review](2026-11-25-hermes-telegram-tg03.md), authorized
by the request to fix all findings. Implementation and isolated verification
only; production deployment/restart and live acceptance remain separate.

**All review findings are remediated in the proposed configuration.** Wildcard
startup is rejected, non-DM callbacks and retained pairing grants cannot bypass
the user list, and native imports/MCP registration pass using the production
disposable-cache configuration. Nothing in this report records deployment.

## Authorization findings fixed

`apps/hermes/runtime_guard/sitecustomize.py` is loaded from a read-only mount via
Compose's pinned `PYTHONPATH`, before Python runs a native CLI or supervised
gateway. It validates the Compose-provided user list before importing the native
authorization mixin. Empty, wildcard, mixed wildcard, malformed, negative,
zero, non-ASCII and oversized IDs are rejected without printing values. The
accepted list is frozen before native dotenv/profile loading. A failure to
initialize the guard stops Python rather than allowing sitecustomize's normal
exception-and-continue behavior.

The small version-dependent integration replaces Telegram's decision at
`GatewayAuthorizationMixin._is_user_authorized`, the shared native runner gate
used by messages, callbacks and platform events. Only listed human users in
their own private DM qualify. Group/forum/channel traffic, mismatched chat IDs,
bots, pairing approvals, global/chat grants and delegated roles cannot expand
this policy. Unauthorized Telegram DMs always use ignore mode. Other platforms
delegate to the original native methods. Existing pairing and pending-prompt
records are retained without deletion or format changes.

The native `run_adapters._wire_adapter_handlers` wires this runner gate into
Telegram's callback authorization. Tests exercise actual native callback handlers
with allowlisted group senders and retained exec/slash/clarify prompt state,
verifying no protected dispatch or claim. A valid private callback still reaches
the native picker. This is code enforcement in the configured Python processes;
it is not a boundary against trusted operators changing mounts/environment,
using Python `-S`, or replacing native code. Revalidate before an image upgrade.

## Authorization verification

- Before applying the guard, the converted rejection tests failed: wildcard,
  retained pairing and five group/missing-context callback cases returned true.
  Command: `python3 scripts/verify_hermes_skills.py` in its offline mode.
- After the fix, the same installed-image harness passed **17 native tests**,
  all four effective platform schema checks, exact fifteen MCP schemas, curated
  skill loading and validation HTTP guard. The native Matrix authorization path
  remains exercised, and its effective schema is unchanged. No Telegram adapter
  connection, model request, Matrix event or production write was made.
- `python3 -m unittest discover -s scripts -p 'test_hermes_telegram*.py'`:
  **7 passed**, including subprocess checks proving invalid configuration stops
  Python before its command runs, sanitized errors, strict policy decisions and
  the read-only guard mount/pinned path in fixture Compose rendering.
- `python3 -m unittest discover -s scripts -p 'test_verify_hermes_skills.py'`:
  **8 passed**. `git diff --check`: **passed**.

Installed image:
`sha256:2f305c9bdc81731f48664586d23cb6a6f838a15ad7be1bfabe0c3c269d8e09b9`.
Private native evidence remains ignored at
`reports/hermes-skills-static-evidence.json`; production container identity/start
state and skill/memory hashes were unchanged.

## Damaged image bytecode remediated

The original image was tested in a disposable no-network container without
production mounts or credentials. Importing `gateway.authz_mixin` and
`gateway.run.GatewayRunner` failed with `ValueError: bad marshal data (unknown
type code)`, including provider-plugin failures. The traceback reached cached
standard-library `urllib.request` bytecode; this was reproducible independently
of the proposed authorization guard.

Compose now sets `PYTHONPYCACHEPREFIX=/tmp/hermes-pycache` and supplies a private
128 MiB tmpfs owned by the installed image's Hermes UID/GID 10000. Each container
start gets a fresh cache, avoiding damaged image `.pyc` files without modifying
the image or deleting anything in native home. MCP's explicit environment now
forwards the same cache path. The verifier's injected `sys.pycache_prefix` bridge
override and its validation-only cache prefix were removed. Live CLI validation
also uses the production cache settings and a fixture Telegram credential,
never the real Telegram bot token.

The updated offline harness passed native CLI and `GatewayRunner` imports,
confirmed the actual runner inherits the installed authorization guard, and
registered all fifteen MCP schemas through the real filtered child environment.
All **17 native Telegram tests** and four platform selections passed under this
configuration. This verifies startup imports and MCP loading, not a full native
service boot or external reachability. The original image remains unchanged.

The full gateway/Matrix fixture suite was rerun after remediation: **148 passed,
zero skipped**, using existing Node 24.14.1 and local HTTP/Unix fixtures. No real
approval event or Docker operation against a production service occurred.

Compatibility: native Hermes is the affected consumer. Telegram grants are
intentionally narrowed to the validated startup list. No MCP/gateway/broker/
Matrix relay API, credential boundary, toolset, native state format or approval/
execution/delivery record changes. Native pairing approvals remain readable but
do not authorize Telegram while the guard is active; Matrix pairing behavior is
unchanged. Rollback disables Telegram and preserves all current state and the
verified cache settings; reverting the cache settings restores the import failure.
Removing only the guard while leaving Telegram enabled would restore the gaps.

No deployment is recorded here. TG-04 still requires operator approval, private
configuration/BotFather checks and authorized live acceptance from the runbook.
