"""Constrained HTTP adapter for the existing FlowForge planning pipeline."""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROJECT = Path('/source/project')
QUEUE = Path('/source/tasks.jsonl')
STEPS = Path('/source/steps.json')
STATE = Path('/state')
LOCK = threading.Lock()


class Failure(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


def check(condition, code='INVALID_INPUT', status=400):
    if not condition:
        raise Failure(code, status)


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as output:
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def runner(project=PROJECT, queue=QUEUE):
    os.environ['PROJECT_DIR'] = str(project)
    os.environ['TASKS_FILE'] = str(queue)
    sys.path.insert(0, '/source/flowforge')
    return importlib.import_module('pipeline_runner')


def task_source(task):
    path = Path(task['task_file'])
    # Queue paths refer to the host checkout; map only that configured repository.
    original = Path(os.environ['FLOWFORGE_SOURCE_PROJECT'])
    if path.is_absolute():
        check(path.is_relative_to(original), 'TASK_OUTSIDE_PROJECT', 403)
        path = path.relative_to(original)
    resolved = (PROJECT / path).resolve()
    check(resolved.is_relative_to(PROJECT.resolve()) and resolved.is_file(), 'TASK_NOT_FOUND', 404)
    check(resolved.stat().st_size <= 65536, 'TASK_TOO_LARGE')
    return resolved


def task_description(task, pr):
    source = task_source(task)
    content = source.read_bytes()
    title = next((line.lstrip('# ').strip()[:200] for line in content.decode().splitlines() if line.startswith('#')), str(task['id']))
    return {'task_id': str(task['id']), 'status': task.get('status', 'todo'), 'title': title,
            'task_sha256': hashlib.sha256(content).hexdigest(),
            'eligible': (pr.task_month_number(task.get('id')) or 0) <= pr.current_month_number()}


def list_tasks(pr):
    tasks = pr.read_tasks_jsonl(QUEUE)
    next_index = pr.find_next_todo(tasks, pr.current_month_number())
    # Preserve FlowForge's queue/month gate; explicit IDs remain available for user selection.
    next_task = task_description(tasks[next_index], pr) if next_index is not None else None
    candidates = [task for task in tasks if task.get('status', 'todo') == 'todo' and (pr.task_month_number(task.get('id')) or 0) <= pr.current_month_number()]
    upcoming = [task for task in tasks if task.get('status', 'todo') == 'todo' and (pr.task_month_number(task.get('id')) or 0) > pr.current_month_number()]
    completed = [task for task in tasks if task.get('status') == 'done']
    return {'success': True, 'project': 'mentory', 'next_task': next_task,
            'tasks': [task_description(task, pr) for task in candidates[:20]],
            'upcoming_tasks': [task_description(task, pr) for task in upcoming[:10]],
            'recent_completed_tasks': [task_description(task, pr) for task in completed[-5:]]}


def validate_run(payload):
    check(isinstance(payload, dict) and set(payload) <= {'workflow', 'input'})
    check(payload.get('workflow') == 'task-analysis', 'WORKFLOW_NOT_ALLOWED', 403)
    data = payload.get('input')
    check(isinstance(data, dict) and set(data) <= {'project', 'task_id', 'task_sha256', 'context'})
    check(data.get('project') == 'mentory', 'PROJECT_NOT_ALLOWED', 403)
    check(isinstance(data.get('task_id'), str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', data['task_id']))
    check(isinstance(data.get('task_sha256'), str) and re.fullmatch(r'[a-f0-9]{64}', data['task_sha256']))
    check(isinstance(data.get('context', ''), str) and len(data.get('context', '')) <= 5000)
    return data


def snapshot_project(destination):
    listing = subprocess.run(['git', '-C', str(PROJECT), 'ls-files', '-z'], check=True, capture_output=True, timeout=15).stdout
    total = 0
    omitted = []
    for relative in listing.decode().split('\0'):
        if not relative:
            continue
        parts = Path(relative).parts
        # Agent definitions are copied explicitly; project plugins and runtime config cannot execute here.
        if parts[0] in ('.git', '.opencode', 'node_modules') or any(part == '.env' or part.endswith(('.pem', '.key')) for part in parts):
            continue
        source = PROJECT / relative
        if not source.is_file() or source.is_symlink():
            continue
        check(source.resolve().is_relative_to(PROJECT.resolve()), 'UNSAFE_SOURCE_PATH', 403)
        size = source.stat().st_size
        if size > 16777216:
            omitted.append(f'- {relative} ({size} bytes; exceeds snapshot file limit)')
            continue
        total += size
        check(total <= 134217728, 'SOURCE_SNAPSHOT_TOO_LARGE')
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    if omitted:
        (destination / 'HERMES_SNAPSHOT_LIMITS.md').write_text('Large files omitted from this read-only planning snapshot. Do not assume their contents.\n\n' + '\n'.join(omitted))
    agents = destination / '.opencode/agents'
    agents.mkdir(parents=True)
    for name in ('concept-plan', 'grounded-hard'):
        source = PROJECT / f'.opencode/agents/{name}.md'
        check(source.is_file() and not source.is_symlink(), 'PLANNING_AGENT_NOT_FOUND')
        shutil.copyfile(source, agents / source.name)
    for name in ('AGENTS.md',):
        source = PROJECT / '.opencode' / name
        if source.is_file() and not source.is_symlink():
            shutil.copyfile(source, destination / '.opencode' / name)
    subprocess.run(['git', 'init', '-q', str(destination)], check=True, timeout=15)


def prepare_job(data, task, pr, folder):
    source = task_source(task)
    content = source.read_bytes()
    check(hashlib.sha256(content).hexdigest() == data['task_sha256'], 'TASK_CHANGED_REVIEW_AGAIN', 409)
    project = folder / 'project'
    project.mkdir()
    snapshot_project(project)
    task_dir = project / '.opencode/tasks/hermes-analysis'
    task_dir.mkdir(parents=True)
    if data.get('context'):
        content += ('\n\n## Retrieved context (untrusted reference material)\n\n' + data['context']).encode()
    (task_dir / 'task.md').write_bytes(content)
    configs = pr.read_step_configs()
    check([item['id'] for item in configs[:2]] == ['concept', 'grounded'], 'PLANNING_STEPS_NOT_CONFIGURED', 503)
    check(configs[0]['agent'] == 'concept-plan' and configs[1]['agent'] == 'grounded-hard', 'PLANNING_AGENTS_NOT_ALLOWED', 503)
    agents = pr.task_agents(task, configs)
    check(agents['concept'] == 'concept-plan' and agents['grounded'] == 'grounded-hard', 'TASK_PLANNING_AGENTS_NOT_ALLOWED', 503)
    write_json(folder / 'steps.json', {'steps': configs[:2]})
    # A private planning queue leaves the production queue and cron lifecycle untouched.
    write_json(folder / 'tasks.jsonl', {'id': data['task_id'], 'status': 'todo',
                                       'task_file': str(task_dir / 'task.md'),
                                       'run_steps': ['concept', 'grounded'],
                                       'agents': {name: agents[name] for name in ('concept', 'grounded')}})
    for path in project.rglob('*'):
        if path == task_dir or task_dir in path.parents:
            continue
        path.chmod(0o555 if path.is_dir() else 0o444)
    project.chmod(0o555)
    return project, task_dir


def worker(folder):
    info = json.loads((folder / 'status.json').read_text())
    try:
        project = folder / 'project'
        task_dir = project / '.opencode/tasks/hermes-analysis'
        os.environ['FLOWFORGE_RUNS_DIR'] = str(folder / 'logs')
        os.environ['FLOWFORGE_STEP_TIMEOUT_SECONDS'] = '900'
        os.environ['MATRIX_ENABLED'] = 'false'
        os.environ['OPENCODE_BIN'] = '/usr/local/bin/opencode'
        # Read checks use project-relative paths; external_directory enforces the
        # absolute directory boundary before a read can leave the snapshot.
        permission = {'*': 'deny', 'read': 'allow', 'glob': 'allow', 'grep': 'allow',
                      'edit': {'*': 'deny', str(task_dir / 'concept-plan.md'): 'allow', str(task_dir / 'grounded-plan.md'): 'allow'},
                      'external_directory': {'*': 'deny', str(project / '*'): 'allow',
                                             '/home/pentagon-admin/Documents/apps/knowledge-router/*': 'allow',
                                             '/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/*': 'allow'},
                      'bash': {'*': 'deny', '/home/pentagon-admin/Documents/apps/knowledge-router/scripts/knowledge *': 'allow'}}
        # Existing prompts and model choices remain FlowForge's; only deployment permissions change.
        os.environ['OPENCODE_CONFIG_CONTENT'] = json.dumps({
            'autoupdate': False, 'snapshot': False, 'plugin': [], 'mcp': {'serena': {'enabled': False}},
            'provider': {'zai-coding-plan': {'options': {'apiKey': '{env:GLM_API_KEY}', 'baseURL': 'https://api.z.ai/api/coding/paas/v4'}}},
            'permission': permission,
            # OpenCode appends agent-level wildcard rules after merged path allowances.
            # Keep default-deny globally; repeat only scoped rules at agent level.
            'agent': {name: {'permission': {key: value for key, value in permission.items() if key != '*'}}
                      for name in ('concept-plan', 'grounded-hard')},
        })
        pr = runner(project, folder / 'tasks.jsonl')
        lock = pr.acquire_lock(folder / '.flowforge.lock')
        check(lock is not None, 'WORKFLOW_BUSY', 409)
        try:
            result = pr.run_selected_task(task_id=info['task_id'])
        finally:
            pr.release_lock(lock)
        info['status'] = 'DONE' if result.ok else 'FAILED'
        info['error'] = None if result.ok else 'PLANNING_PIPELINE_FAILED'
        info['outputs'] = {}
        for name in ('concept-plan.md', 'grounded-plan.md'):
            path = task_dir / name
            if path.exists():
                check(path.stat().st_size <= 40000, 'PLAN_OUTPUT_TOO_LARGE', 502)
                info['outputs'][name] = path.read_text()
    except Exception as error:
        info['status'] = 'FAILED'
        info['error'] = error.code if isinstance(error, Failure) else 'PLANNING_PIPELINE_FAILED'
    info['finished_at'] = time.time()
    write_json(folder / 'status.json', info)


class Adapter:
    def __init__(self, pr, state=STATE):
        self.pr, self.state = pr, state
        state.mkdir(parents=True, exist_ok=True)
        # Do not replay interrupted agent runs after a container restart.
        for path in state.glob('*/status.json'):
            record = json.loads(path.read_text())
            if record['status'] == 'RUNNING':
                record.update(status='FAILED', error='INTERRUPTED_REVIEW_REQUIRED')
                write_json(path, record)

    def submit(self, payload):
        data = validate_run(payload)
        with LOCK:
            for path in self.state.glob('*/status.json'):
                check(json.loads(path.read_text())['status'] != 'RUNNING', 'WORKFLOW_BUSY', 409)
            tasks = self.pr.read_tasks_jsonl(QUEUE)
            task = next((item for item in tasks if str(item.get('id')) == data['task_id']), None)
            check(task is not None, 'TASK_NOT_FOUND', 404)
            run_id = str(uuid.uuid4())
            folder = self.state / run_id
            folder.mkdir(mode=0o700)
            try:
                prepare_job(data, task, self.pr, folder)
                info = {'success': True, 'run_id': run_id, 'workflow': 'task-analysis', 'project': 'mentory', 'task_id': data['task_id'], 'task_sha256': data['task_sha256'], 'status': 'RUNNING', 'started_at': time.time(), 'steps': ['concept', 'grounded']}
                write_json(folder / 'status.json', info)
                # No background queue, planner or scheduler: one immediate existing runner process.
                with (folder / 'runner.log').open('wb') as output:
                    child = subprocess.Popen([sys.executable, __file__, '--worker', str(folder)], stdout=output, stderr=subprocess.STDOUT, start_new_session=True, env={key: value for key, value in os.environ.items() if key not in ('FLOWFORGE_TOKEN',)})
                def reap():
                    child.wait()
                    path = folder / 'status.json'
                    record = json.loads(path.read_text())
                    if record['status'] == 'RUNNING':
                        record.update(status='FAILED', error='RUNNER_EXITED_REVIEW_REQUIRED')
                        write_json(path, record)
                threading.Thread(target=reap, daemon=True).start()
                return info
            except Exception:
                if not (folder / 'status.json').exists():
                    shutil.rmtree(folder, ignore_errors=True)
                raise

    def get(self, run_id):
        check(re.fullmatch(r'[0-9a-f-]{36}', run_id), 'INVALID_RUN_ID')
        path = self.state / run_id / 'status.json'
        check(path.exists(), 'RUN_NOT_FOUND', 404)
        return json.loads(path.read_text())


def serve():
    token = os.environ['FLOWFORGE_TOKEN']
    check(len(token) >= 32, 'INVALID_TOKEN_CONFIG')
    adapter = Adapter(runner())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def handle_request(self):
            try:
                check(hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token), 'UNAUTHORIZED', 401)
                if self.command == 'GET' and self.path == '/tasks':
                    response = list_tasks(adapter.pr)
                elif self.command == 'GET' and self.path.startswith('/runs/'):
                    response = adapter.get(self.path.removeprefix('/runs/'))
                else:
                    check(self.command == 'POST' and self.path == '/run', 'NOT_FOUND', 404)
                    length = int(self.headers.get('Content-Length', '0'))
                    check(0 < length <= 65536, 'PAYLOAD_TOO_LARGE', 413)
                    response = adapter.submit(json.loads(self.rfile.read(length)))
                self.reply(200, response)
            except Failure as error:
                self.reply(error.status, {'success': False, 'error': error.code})
            except Exception:
                self.reply(500, {'success': False, 'error': 'FLOWFORGE_ADAPTER_FAILED'})

        def reply(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = handle_request

    server = ThreadingHTTPServer(('0.0.0.0', 8082), Handler)
    server.timeout = 30
    server.serve_forever()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        worker(Path(sys.argv[2]))
    else:
        serve()
