"""Operator acceptance recorder for the installed Hermes native memory tool.

Runs normal CLI sessions in the existing container; never writes memory files.
Only test entries, aggregate counts, and hashes leave the container. Run each
stage separately so failures can be reported before any attempted remediation.
"""
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

CONTAINER = "personal-agent-hermes-1"
ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "reports/hermes-memory-evidence.json"
MARKER = "memory acceptance test"
COMPACT = "For the memory acceptance test, my preferred report format is compact."
DETAILED = "For the memory acceptance test, my preferred report format is detailed."
PROMPTS = {
    "save": (
        "This is an explicitly authorized temporary persistent-memory acceptance test. "
        "Save exactly this separate test preference through your native memory tool, "
        "target=user: “" + COMPACT + "” "
        "Despite its temporary test scope, persist it for this acceptance test; it will "
        "be explicitly removed later. Preserve every existing memory unchanged. "
        "Use only the native memory tool for this request. Do not print other memories."
    ),
    "recall_compact": (
        "Read your session-start persistent memory. What is my preferred report format "
        "for the memory acceptance test? Reply with only the test label and current "
        "value, or ABSENT if no such preference is present. Do not search conversation "
        "history, call tools, or modify memory. Do not disclose other memories."
    ),
    "correct": (
        "Correct the temporary persistent preference labelled 'memory acceptance test': "
        "my preferred report format for that test is now detailed. Use the native "
        "memory tool to patch that single test entry in target=user. Keep its test "
        "label. The previous value is superseded and must not remain current. Preserve "
        "all unrelated memories unchanged. Use only the memory tool; print no other memories."
    ),
    "remove": (
        "The memory acceptance test is complete. Through the native memory tool, remove "
        "only the temporary preference labelled 'memory acceptance test' from active "
        "persistent memory. Preserve all unrelated memories unchanged. Use only the "
        "memory tool. Do not print other memories. Historical conversations may retain it."
    ),
}
for _stage in ("recall_detailed", "recall_after_restart", "recall_after_remove"):
    PROMPTS[_stage] = PROMPTS["recall_compact"]

# This observer only reads native files / SQLite; MemoryStore.load_from_disk is
# the installed parser and frozen-snapshot loader. Mutations belong to Hermes.
OBSERVE = r'''
import hashlib,json,sqlite3,sys
from pathlib import Path
from tools.memory_tool import load_on_disk_store
marker="memory acceptance test"
def digest(x): return hashlib.sha256(x.encode() if isinstance(x,str) else x).hexdigest()
def test(x): return marker in x.lower()
def lines(x): return [l for l in (x or "").splitlines() if test(l)]
s=load_on_disk_store()
result={"stores":{}}
for target in ("user","memory"):
 p=s._path_for(target); entries=s._entries_for(target)
 result["stores"][target]={"path":str(p),"exists":p.exists(),
  "sha256":digest(p.read_bytes()) if p.exists() else None,
  "entry_count":len(entries),"unrelated_entry_sha256":[digest(x) for x in entries if not test(x)],
  "test_entries":[x for x in entries if test(x)],
  "frozen_snapshot_test_lines":lines(s._system_prompt_snapshot[target])}
result["configuration_sha256"]={str(p):digest(p.read_bytes()) for p in
 [Path('/opt/data/config.yaml'),Path('/opt/data/SOUL.md')]}
g=json.loads(Path('/opt/data/gateway_state.json').read_text())
result["gateway"]={k:g.get(k) for k in ('gateway_state','active_agents','updated_at')}
result["gateway"]["active_work_count"]=len(g.get('active_work') or [])
from gateway.status import runtime_status_pid_is_live,runtime_status_heartbeat_age_s
result["gateway"]["pid_live"]=runtime_status_pid_is_live(g)
result["gateway"]["heartbeat_age_s"]=runtime_status_heartbeat_age_s(g)
a=json.loads(Path('/opt/data/runtime/active_sessions.json').read_text())
result['runtime_active_session_count']=len(a.get('entries') or [])
jobs=json.loads(Path('/opt/data/cron/jobs.json').read_text()).get('jobs',[])
result['cron']={'job_count':len(jobs),'enabled_count':sum(bool(j.get('enabled')) for j in jobs),
 'running_count':sum(bool(j.get('fire_claim') or j.get('last_status')=='running') for j in jobs)}
prompt=sys.argv[1] if len(sys.argv)>1 else ''
if prompt:
 c=sqlite3.connect('file:/opt/data/state.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
 rows=c.execute("""SELECT s.*, COALESCE(p.prompt,s.system_prompt) AS resolved_prompt
 FROM sessions s LEFT JOIN system_prompts p ON p.hash=s.system_prompt_hash
 WHERE s.id IN (SELECT session_id FROM messages WHERE role='user' AND content=?)
 ORDER BY s.started_at DESC""",(prompt,)).fetchall()
 sessions=[]
 def safe_result(raw):
  try: obj=json.loads(raw)
  except (ValueError,TypeError): return {'unparsed_result_sha256':digest(raw or '')}
  def scrub(x):
   if isinstance(x,dict):
    return {k:([v for v in val if isinstance(v,str) and test(v)] if k in
     ('current_entries','entries','memory_entries','user_entries') and isinstance(val,list)
     else scrub(val)) for k,val in x.items()}
   if isinstance(x,list): return [scrub(v) for v in x]
   return x
  # Responses can contain full rendered stores; expose only matching test lines.
  for k in list(obj):
   if k in ('memory','user','content') and isinstance(obj[k],str):
    obj[k]={'test_lines':lines(obj[k]),'sha256':digest(obj[k])}
  return scrub(obj)
 for row in rows[:1]:
  msgs=[dict(x) for x in c.execute('SELECT role,content,tool_calls,tool_call_id,tool_name FROM messages WHERE session_id=? ORDER BY id',(row['id'],))]
  calls=[]; outputs=[]; answers=[]
  for m in msgs:
   if m['tool_calls']:
    tc=json.loads(m['tool_calls'])
    for call in tc:
     f=call.get('function',{});args=f.get('arguments',{})
     if isinstance(args,str): args=json.loads(args)
     calls.append({'id':call.get('id'),'name':f.get('name'),'arguments':args})
   if m['role']=='tool': outputs.append({'tool_call_id':m['tool_call_id'],'tool_name':m['tool_name'],'result':safe_result(m['content'])})
   if m['role']=='assistant' and m['content']:
    # The prompt requests only test-specific output. Keep it scoped even if ignored.
    answers.extend(l for l in m['content'].splitlines() if test(l) or l.strip().lower() in
      ('compact','detailed','absent','compact.','detailed.'))
  sessions.append({'id':row['id'],'parent_session_id':row['parent_session_id'],
   'source':row['source'],'model':row['model'],'started_at':row['started_at'],
   'ended_at':row['ended_at'],'message_count':len(msgs),
   'user_message_count':sum(m['role']=='user' for m in msgs),
   'system_prompt_test_lines':lines(row['resolved_prompt']),
   'tool_calls':calls,'tool_results':outputs,'test_answer_lines':answers})
 result['sessions']=sessions
print(json.dumps(result))
'''


def docker(*args, input=None, timeout=60):
    result = subprocess.run(["docker", *args], input=input, text=True,
                            capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"docker operation failed ({result.returncode}); output suppressed for privacy")
    return result.stdout


def observe(prompt=""):
    return json.loads(docker("exec", "-i", CONTAINER, "python", "-", prompt, input=OBSERVE))


def container_states():
    ids = docker("ps", "-aq").split()
    rows = docker("inspect", *ids, "--format",
        '{"name":{{json .Name}},"id":{{json .Id}},"started_at":{{json .State.StartedAt}},"running":{{json .State.Running}}}')
    return {row["name"].lstrip("/"): row for row in map(json.loads, rows.splitlines())}


def main():
    stage = sys.argv[1]
    evidence = json.loads(EVIDENCE.read_text()) if EVIDENCE.exists() else {"stages": []}
    record = {"stage": stage, "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if stage == "baseline":
        if evidence["stages"]:
            raise RuntimeError("Refusing to overwrite prior evidence")
        record["version"] = docker("exec", CONTAINER, "hermes", "--version").strip()
        record["image"] = json.loads(docker("inspect", CONTAINER, "--format",
            '{{json .Image}}'))
    elif stage in PROMPTS:
        prompt = PROMPTS[stage]
        record["prompt"] = prompt
        record["command"] = ["docker", "exec", "-i", CONTAINER, "hermes", "chat",
                             "--query-file", "-", "--format", "stream-json"]
        # No model, permissions, toolset, resume, or configuration overrides.
        result = subprocess.run(record["command"], input=prompt, text=True,
                                capture_output=True, timeout=360)
        record["cli_exit_code"] = result.returncode
        record["cli_stdout_bytes"] = len(result.stdout.encode())
        record["cli_stderr_bytes"] = len(result.stderr.encode())
    elif stage == "restart":
        record['before'] = observe()
        g = record['before']['gateway']
        idle = (g['gateway_state'] == 'running' and g['pid_live'] and
                g['heartbeat_age_s'] is not None and g['heartbeat_age_s'] < 30 and
                g['active_agents'] == 0 and g['active_work_count'] == 0 and
                record['before']['runtime_active_session_count'] == 0 and
                record['before']['cron']['enabled_count'] == 0 and
                record['before']['cron']['running_count'] == 0)
        record['active_work_check_passed'] = idle
        if not idle:
            raise RuntimeError('Hermes is busy or status is uncertain; restart not attempted')
        before = container_states()
        record['command'] = ['docker', 'restart', '--time', '30', CONTAINER]
        docker('restart', '--time', '30', CONTAINER, timeout=60)
        record['container_states_before'] = before
        record['container_states_after'] = after = container_states()
        record['other_containers_unchanged'] = all(
            after.get(name) == state for name, state in before.items() if name != CONTAINER)
        record['hermes_same_container'] = before[CONTAINER]['id'] == after[CONTAINER]['id']
        record['hermes_start_time_changed'] = before[CONTAINER]['started_at'] != after[CONTAINER]['started_at']
        for attempt in range(60):
            try:
                ready = observe()['gateway']
                if ready['gateway_state'] == 'running' and ready['pid_live']:
                    break
            except (RuntimeError, json.JSONDecodeError):
                pass
            time.sleep(1)
        else:
            record['startup_failed'] = True
    elif stage != "inspect":
        raise ValueError(stage)
    record["observed"] = observe(PROMPTS.get(stage, ""))
    if evidence["stages"]:
        baseline = evidence["stages"][0]["observed"]
        record["unrelated_entries_preserved"] = all(
            record["observed"]["stores"][t]["unrelated_entry_sha256"] ==
            baseline["stores"][t]["unrelated_entry_sha256"] for t in ("user", "memory"))
        record["configuration_unchanged"] = (record["observed"]["configuration_sha256"] ==
                                               baseline["configuration_sha256"])
    evidence["stages"].append(record)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
