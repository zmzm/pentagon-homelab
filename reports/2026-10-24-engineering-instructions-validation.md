# Initial engineering-instructions validation — 2026-10-24

This is historical evidence from the initial documentation change, moved out of
the engineering guide during its later refinement. These checks were not rerun
as part of that move and do not establish the status of a later checkout or deployment.

- Original validation date: **2026-10-24**.
- Tested implementation revision: **`a5a74386f0d65f586d924dde68f413d23e44ba62`**.
- Initial documentation commit: **`c85c193`** (tests ran before that commit).
- Shared Coding Vault revision used: **`0f3abe5374c5ad2ec4bd11fe4788819eb0c0e55d`**.

## Recorded checks and limits

No pre-existing AGENTS.md was found in this repository or its inspected ancestor
directories. The shared vault's applicable navigation/rules were read and retained.
The new files were checked against the implementation/tests linked from the
[engineering guide](../docs/engineering.md#component-responsibilities-and-sources-of-truth).

- Node 24.14.1 `npm test`: **81 passed, 0 skipped**, including actual external
  Knowledge Router retrieval and fake-socket restart deadlines. The initial
  restricted-environment run failed at file level without useful diagnostics;
  the rerun with local fixture socket access passed.
- Adapter unittest: **7 passed**, including the existing runner with mocked model
  boundary. Skill-checker unittest: **8 passed**.
- Bridge unittest in a disposable no-network installed-image container:
  **2 passed, 1 error**. The native `Tool` exposes `input_schema`, while the fixture
  accesses `inputSchema`. Host Python lacks MCP/Pydantic; no dependencies installed.
- Offline skill harness: **passed**, including installed native registration,
  exact skill loading, all platform selections and production isolation checks.
  Read-only deployed MCP handshake/discovery/Vaultwarden inspection: **passed**.
- Compose quiet validation: **passed**. Read-only homelab snapshot check before
  committing: **ready, unchanged, not stale** at the tested implementation revision
  recorded above.
  Committing changes Git revision metadata, which requires a later operator
  refresh for `--check` to report current again; no production snapshot/index rebuilt.
- Relative file/anchor links, command paths and whitespace were checked locally.
  Paid/live skill behavior, native state-producing FlowForge preflight, Matrix
  approval/attachment sends, service restarts/deployment and live acceptance were
  **not run**. Prior reports were not substituted for these checks.
