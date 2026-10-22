"""Run inside the planning API: validate real snapshot/config without invoking an LLM."""
import json
import os
from pathlib import Path
import subprocess
import uuid
import adapter

pr = adapter.runner()
tasks = pr.read_tasks_jsonl(adapter.QUEUE)
completed = [task for task in tasks if task.get('status') == 'done']
task = completed[-1] if completed else tasks[0]
description = adapter.task_description(task, pr)
folder = adapter.STATE / 'preflight' / str(uuid.uuid4())
folder.mkdir(parents=True)
# Native debug commands must never share the live agent's session database.
os.environ['XDG_DATA_HOME'] = str(folder / 'opencode-data')
project, task_dir = adapter.prepare_job({'project': 'mentory', **description}, task, pr, folder)
adapter.write_json(folder / 'status.json', {'task_id': description['task_id'], 'status': 'RUNNING'})


def validate_only(**_kwargs):
    # The existing runner's model call is never invoked in this preflight.
    result = subprocess.run(['/usr/local/bin/opencode', 'debug', 'config'], cwd=project,
                            capture_output=True, text=True, timeout=45)
    if result.returncode:
        # Return only configuration parser errors, never config/provider values.
        for line in result.stderr.splitlines():
            if 'Unrecognized key' in line or 'Invalid input' in line:
                print(line[:250])
        raise RuntimeError('OpenCode rejected the planning configuration')
    config = json.loads(result.stdout)
    assert config['mcp']['serena']['enabled'] is False
    for name in ('concept-plan', 'grounded-hard'):
        permissions = config['agent'][name]['permission']
        assert permissions['bash']['*'] == 'deny'
        assert permissions['edit']['*'] == 'deny'
    for name, output_name in (('concept-plan', 'concept-plan.md'), ('grounded-hard', 'grounded-plan.md')):
        inspected = subprocess.run(['/usr/local/bin/opencode', 'debug', 'agent', name],
                                   cwd=project, capture_output=True, text=True, timeout=30)
        assert inspected.returncode == 0, 'Cannot inspect effective planning tools'
        tools = json.loads(inspected.stdout)['tools']
        if not all(tools.get(key) for key in ('read', 'write', 'edit')):
            print('FAIL: actual planning agent has no read/write/edit tools', flush=True)
            raise AssertionError('Plan reading/writing tools are disabled')
        assert not any(tools.get(key) for key in ('task', 'webfetch', 'skill', 'question')), 'Unexpected planning capabilities'
        if name == 'grounded-hard':
            assert tools.get('grep'), 'Grounded planning cannot search code'
        read = subprocess.run(['/usr/local/bin/opencode', 'debug', 'agent', name,
                               '--tool', 'read', '--params', json.dumps({'filePath': str(task_dir / 'task.md')})],
                              cwd=project, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        assert read.returncode == 0, 'Actual OpenCode task read failed'
        outside = subprocess.run(['/usr/local/bin/opencode', 'debug', 'agent', name,
                                  '--tool', 'read', '--params', json.dumps({'filePath': '/etc/hostname'})],
                                 cwd=project, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        assert outside.returncode != 0, 'Read outside allowlisted directories was permitted'
        target = task_dir / output_name
        assert not target.exists(), 'Never overwrite an existing plan in preflight'
        text = '# FlowForge isolated write probe\n'
        denied = task_dir / 'not-a-plan.permission-probe.md'
        try:
            written = subprocess.run(['/usr/local/bin/opencode', 'debug', 'agent', name,
                                      '--tool', 'write', '--params', json.dumps({'filePath':str(target), 'content':text})],
                                     cwd=project, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
            assert written.returncode == 0 and target.read_text() == text, 'Actual OpenCode plan save failed'
            blocked = subprocess.run(['/usr/local/bin/opencode', 'debug', 'agent', name,
                                      '--tool', 'write', '--params', json.dumps({'filePath':str(denied), 'content':'must not write'})],
                                     cwd=project, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
            assert blocked.returncode != 0 and not denied.exists(), 'Undesignated output path was permitted'
        finally:
            for path in (target, denied):
                if path.exists():
                    path.unlink()
    blocked_shell = subprocess.run(['/usr/local/bin/opencode', 'debug', 'agent', 'concept-plan',
                                    '--tool', 'bash', '--params', json.dumps({'command':'printf flowforge-deny-probe', 'description':'Verify arbitrary shell remains denied'})],
                                   cwd=project, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    assert blocked_shell.returncode != 0, 'Arbitrary shell execution was permitted'
    print('PASS: actual OpenCode tools read tasks, deny outside reads, save both designated plans, reject undesignated files and deny arbitrary shell')
    print('PASS: installed OpenCode accepts isolated planning config and denies arbitrary shell/repository edits')
    return pr.RunResult(True, description['task_id'], None, None, 'configuration-only preflight')


pr.run_selected_task = validate_only
adapter.runner = lambda *_args: pr
os.environ.pop('FLOWFORGE_TOKEN', None)
adapter.worker(folder)
record = json.loads((folder / 'status.json').read_text())
assert record['status'] == 'DONE', record.get('error')
print('PASS: source snapshot and existing agent/model configuration prepared without executing a model or modifying the source queue')
