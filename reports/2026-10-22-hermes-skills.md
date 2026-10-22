# Hermes native skills: deployment and readable diagnosis acceptance

On 2026-10-22, the reviewed native skill integration was deployed successfully.
Acceptance covers both isolated CLI behavior and real messages from the
authorized user in the existing Matrix conversation. The user accepted the
revised short English answers and clarification behavior. Diagnostic requests
made no write operations or approval requests.

## Integration and deployment

The initial deployment confirmed a clean checkout through `8d7388a`, checked
native gateway liveness and idle state, and validated Docker Compose. Only
Hermes was recreated using `docker compose up -d --no-deps --force-recreate hermes`.
Other containers retained their IDs and start times. Native readiness and Matrix
connection were confirmed, and the deployed tool-registration verifier passed.
The installed image was retained; no upgrade was performed.

The installed Hermes v0.22.3 runtime was the source of truth. Its native skill
index and `skills_list` discover the curated external directory, and `skill_view`
loads `homelab-service-diagnosis`. A small native plugin exposes only the two
skill read tools through `homelab-skills-read`; `skill_manage` is excluded. Skill
discovery/loading requires no terminal, general file, code execution, browser
or delegation tool. Those capabilities remain disabled. Inline shell expansion,
lazy dependency installation and background skill maintenance remain disabled.

The repository skill and plugin are read-only mounts. Existing writable Hermes
state remains mounted; pre/post-deployment memory and runtime-skill file hashes
matched. The allowlisted homelab knowledge projection was refreshed and checked
after the initial deployment, recording `8d7388a` with clean documentation,
ready/not-stale state and no detected source changes at that check.

## Readable replies and retained evidence

The initial technically detailed answer was unsuitable for everyday use. The
skill and SOUL now request a practical assessment first, a small amount of
relevant evidence, material uncertainty and the next useful action. Routine
healthy replies use two or three short paragraphs, at most 150 words. English
remains the response language. Guidance is attributed with readable labels;
exact source references and technical detail remain available when useful or
requested and in retained native results.

Matrix uses the installed native display settings:

```yaml
display:
  platforms:
    matrix:
      tool_progress: log
      interim_assistant_messages: false
      show_reasoning: false
```

Tool progress is retained in the native rotating, redacted tool log rather than
posted into chat. Native session tool results and gateway audit are also kept.
These settings change presentation without expanding tool permissions. The
installed configuration loader/resolver confirmed the settings. Real Matrix
events subsequently confirmed that tool-progress and intermediate commentary
were hidden while final answers and clarification questions were delivered.

## Acceptance results

| Check | Observed result |
| --- | --- |
| Native skill loading | Actual Matrix `skill_view` loaded the current curated skill; returned content hash matched the repository file. |
| Vaultwarden diagnosis | Existing MCP inspection, a bounded 100-line log tail and `project="homelab"` retrieval with limit 5; three successful gateway reads. |
| Readable English answer | Final Matrix answer was 147 words in three paragraphs; the user confirmed it was satisfactory. |
| Evidence separation | Runtime facts came from inspection/logs; recovery guidance was attributed to documentation. Device access and current backup success remained explicitly unverified. |
| Ambiguous Matrix target | A clarification question was delivered. No personal MCP calls occurred before the authorized user's actual choice of the homeserver. |
| Diagnostic side effects | Native calls and gateway audit showed no write operation or approval request in the reviewed diagnostic requests. |
| Tool permissions | Effective CLI/Matrix/cron checks retained native skill reads and existing MCP tools while excluding prohibited tools and `skill_manage`. |
| Validation isolation | Disposable CLI sessions used the configured GLM provider and guarded read-only gateway access without Matrix credentials; production containers and runtime memory/skills remained unchanged. |

Three isolated live CLI iterations were reviewed manually as well as checked
automatically. Earlier replies remained too verbose, so the writing policy was
tightened. The final CLI diagnostic answer was 141 words; its ambiguous case
asked for clarification without personal MCP calls. The test prompts now match
the actual Matrix acceptance requests rather than explicitly asking for a
technical report. The HTTP guard, write-attempt detection and production
isolation were preserved. Final narrow wording refinements were subsequently
exercised through the real Matrix turn, which loaded the exact current skill.

Additional checks passed: skill structural validation, the six validation-harness
regression tests, Compose validation and whitespace checks. Behavioral coverage
is **CLI and Matrix**; cron coverage is effective tool selection only.

## Findings and limits

Recreating Hermes does not refresh instructions saved in an existing
conversation. The first Matrix attempts reused an old prompt, did not select
the new skill and searched the wrong knowledge project. Those attempts failed
acceptance and were retained as failed evidence. Fresh user-controlled sessions
resolved this issue without deleting persistent memory or runtime skills.

For a fresh Matrix session, send standalone `!new` without a bot mention or
display-name prefix, choose **Approve Once** if prompted, and wait for the reset
confirmation. A mention pill can leave a display-name prefix that causes the
command to be treated as chat. The native session-reset confirmation is separate
from diagnostic tool approvals. No user events were manufactured, and the
operator did not reset the user's session or disable the confirmation guard.

The accepted answer has one minor factual wording limitation: it calls the
documented recovery-test pass a scheduled run. The source records a pass directly
and through the installed weekly service; automatic scheduling on that date was
not established. A documented recovery test also does not prove today's backup
succeeded. Container health and sampled logs do not establish end-to-end access,
continuous historical health, database correctness or backup success.

Write tools remain available for separately requested actions. Read-only diagnosis
is enforced by instructions and verified behavior, rather than a production
per-request removal of write schemas. The isolated validation guard blocks any
attempted write before it reaches production and fails acceptance if attempted.

## Publication and operation

The writing/display updates were already visible through existing bind mounts.
A conditional restart check found Hermes idle, running and connected to Matrix;
mounted file hashes matched the repository. No additional restart was needed or
performed. The user started the fresh conversation used for final acceptance.

Publishing the updated allowlisted Hermes README requires refreshing/checking
the homelab knowledge projection from the committed checkout using the procedure
in [the Hermes guide](../apps/hermes/README.md#homelab-documentation).
That operation needs no service restart. Saved conversations may retain older
instructions; use a fresh user-controlled session when validating later changes.

Full native/Matrix/gateway evidence and unsuccessful attempts remain in private,
Git-ignored local reports. This report omits credentials, user/room/event/session
identifiers, memory contents and raw service logs.
