# FlowForge planning API

This adapter exposes the existing FlowForge runner without changing its source, production
queue or timers. It supports one workflow: `task-analysis`, using the existing `concept`
and `grounded` steps and existing planning-agent prompts/model choices. It never includes
the `execution` step.

Files over 16 MiB are omitted with an explicit snapshot manifest; total copied source is capped at 128 MiB.

The source Mentory repository, source task queue and four required FlowForge modules
are mounted read-only. Only the central library’s `concept-plan` and `grounded-hard`
agent files are mounted, under `/source/planning-agents`; project agent copies are
not used. Set `FLOWFORGE_AGENT_LIBRARY_PATH` to the imported private FlowForge library
(default `/home/pentagon-admin/.config/flowforge/library`). No execution-agent
definitions, complete `.env` files, or project plugins are mounted as runner resources.
Each accepted run copies the tracked working-tree files into a private snapshot under
`data/flowforge-api/<run-id>/project`, copies the selected task, and creates a private
planning-only task queue. Source files in that snapshot are read-only too; only its plan
output directory is writable. OpenCode permissions allow only planning outputs, reading/
searching and the existing Knowledge Router wrapper. No production queue status is changed.

The adapter mounts the FlowForge Python modules, central planning agents, task queue
and steps config, not the
FlowForge `.env` or unrelated credentials. It receives only its API token and GLM key;
the API token is removed from the planning child environment. Project plugins and execution
agents are not copied. Serena is disabled in the isolated snapshot; grounding uses ordinary
code reading/search rather than a semantic MCP backend. Existing production configuration
and Serena setup are unchanged.

No planner, pipeline, generic agent runtime, scheduler or task bus is implemented here.
The only new state is a bounded-input HTTP run wrapper around `pipeline_runner.run_selected_task`.

The runner receives an explicit `RuntimeContext` for the private snapshot, queue,
workflow and log directory, with a 900-second timeout. No project environment variables
are changed to select a job. Its compatibility execution mode intentionally retains
the native `OPENCODE_CONFIG_CONTENT` permission overrides: the registered production
project and central default three-step workflow are never selected by a worker. The
private workflow, task step selection and agents are rechecked before execution;
missing private configuration or an execution step fails closed. Execution uses the
shared canonical workspace/queue locks in addition to the adapter’s single-run state.

HTTP/MCP response fields and stored `status.json` records are unchanged. Existing
private run records remain readable; interrupted runs are still failed for review
without replay. The gateway, approval checks, relay and sanitization contract do not
change. A missing central planning agent is an explicit preparation failure, with
no fallback to Mentory’s old agent directory.

## API

All endpoints require the independent `FLOWFORGE_TOKEN` bearer credential and are internal.

- GET `/tasks`: eligible tasks, source content hashes and FlowForge's next eligible task.
  Selection preserves its existing month gate; future tasks require an explicit ID.
- POST `/run`: `{workflow:"task-analysis",input:{project:"mentory",task_id,task_sha256,context?}}`.
  Context is a concise Knowledge Router excerpt/summary (max 5000 characters).
- GET `/runs/:id`: `RUNNING`, `DONE` or `FAILED`, plus completed planning outputs.

The content hash binds the approved request to the exact source task. A changed task fails
before snapshotting or execution. One run can execute at a time; there is no waiting queue.
Each step has a 15-minute timeout. The HTTP call acknowledges a run promptly; clients read
its status rather than holding a long tool call open. Interrupted runs are marked failed
for review and never replayed automatically. Plans are at most 40 KB each in API results.

The gateway classifies submission as CONFIRM and task/status reads as READ. The trusted
Matrix approval listener executes approved requests and polls their specific run, delivering
completed plans to the same room as full UTF-8 Markdown attachments plus one deterministic
completion notice. Attachments use only the gateway-redacted API response; raw files in
this adapter's state directory are never attached. Incomplete delivery retains complete
available sanitized text and a failure record in relay state, with a bounded text fallback.
See [delivery, retries and recovery](../hermes/README.md#planning-result-delivery).
An accepted run is not the same as a completed plan.

## Verification

```bash
python3 -m unittest discover -s apps/flowforge -p 'test_*.py'
```

The twelve tests cover input/path/hash boundaries, private snapshot isolation, restart
handling, central agent selection, fail-closed planning selection, canonical lock
conflicts, and the actual existing FlowForge runner with its process boundary mocked.
An isolated subprocess copies exactly the Python modules declared in Compose and
runs two private jobs with stale production environment values, checking 900-second
timeouts and preserved step models. It does not mount real queues or call a model. The
real-runner integration test requires the sibling FlowForge checkout; otherwise it skips.
The native container preflight additionally checks the actual OpenCode agent tool inventory,
reads the selected task and saves/removes diagnostic files through the real tools for both
planning agents, and verifies outside reads, undesignated file writes and arbitrary shell
commands are denied. The preflight uses a separate OpenCode data directory so its debug
commands cannot share the live session database. It invokes no LLM:

```bash
cd apps/hermes
docker compose exec -T flowforge-api python3 - < ../../scripts/verify_flowforge_preflight.py
```

Default-deny is declared globally. Scoped rules are repeated at agent level without another
`*` rule: OpenCode's merge of agent Markdown/runtime settings can append that duplicate
wildcard after the path allowances and hide read/write/edit tools. Configuration parsing
alone does not catch that failure; the native preflight exercises the effective tools.
Read rules are evaluated relative to the project. The read tool is enabled while
`external_directory` constrains absolute access to the snapshot and the two knowledge
directories; the preflight checks both allowed and denied real reads.
Live GLM planning requires user approval of a concrete task in Matrix.

OpenCode runtime overrides and output-path permission rules follow its
[configuration](https://opencode.ai/docs/config/) and
[permission documentation](https://opencode.ai/docs/permissions/).

## Applying this update

The adapter image contains adapter.py, while Compose mounts the engine and its
dependencies. Updating only the engine file is insufficient. The module mounts are
`pipeline_runner.py`, `flowforge_config.py`, `flowforge_storage.py` and
`flowforge_status.py`; keep this set aligned with the runner’s compatibility path.
The isolated mounted-module test checks that dependency boundary.

Before a separately authorized rollout, ensure the central planning-agent files
exist and run `docker compose config --quiet` from apps/hermes. Rebuild/recreate only
flowforge-api according to the repository rollout procedure, preserving all state
and allowing any active planning/delivery work to finish. Run the native planning
preflight after rollout; unit tests do not establish deployed OpenCode tool behavior.
No production task, approval, paid planning call or Matrix event is required for the
source/unit checks above.

## Hermes operational knowledge

The searchable operator/agent runbook is in
[Hermes's FlowForge guidance](../hermes/README.md#flowforge-task-analysis-isolated-planning-and-approvals).
That README is part of the existing homelab knowledge allowlist; this adapter README
is not followed automatically by the projection. Refresh the existing homelab
snapshot after changing the runbook, then verify a `project="homelab"` retrieval
with original source citations. No new source allowlist, native skill, tool or
permission is needed.

The adapter was rebuilt/recreated on 2026-10-26. Gateway task listing and the native
OpenCode tool preflight passed; the production queue and prior run records were
unchanged. No model call or live Matrix attachment test was part of that rollout.
