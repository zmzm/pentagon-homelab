"""Read-only HTTP facade over FlowForge's project inspection functions.

Run separately from the planning worker: no writable state or model credentials.
Each request has a fixed child command and timeout, never a caller-supplied CLI.
"""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IDENTIFIER = re.compile(r'[a-zA-Z0-9_-]{1,100}')
ACTIONS = {'project', 'catalog', 'status', 'doctor', 'sync-preview'}
MAX_OUTPUT = 120000


class InspectionError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


def require(ok, code='INVALID_INPUT', status=400):
    if not ok:
        raise InspectionError(code, status)


def allowed_projects():
    projects = os.environ.get('FLOWFORGE_READ_PROJECTS', '').split(',')
    require(all(IDENTIFIER.fullmatch(p) for p in projects), 'INVALID_PROJECT_ALLOWLIST', 503)
    return set(projects)


def bounded_text(value, limit=500):
    return str(value)[:limit] if value is not None else None


def inspect(action, project=None):
    # Imports load no dotenv and do not select a legacy project or run agents.
    sys.path.insert(0, os.environ.get('FLOWFORGE_RUNNER_DIR', '/source/flowforge'))
    import pipeline_runner as pr
    from flowforge_config import config_home, list_projects, resolve_context
    allowed = allowed_projects()
    if action == 'projects':
        projects = list_projects()
        require(len(projects) <= 100, 'CATALOG_TOO_LARGE', 502)
        return {'scope': 'configured_read_access', 'projects': [
            {'project': p['id'], 'access': 'READ'} for p in projects if p['id'] in allowed]}
    require(action in ACTIONS and isinstance(project, str) and IDENTIFIER.fullmatch(project))
    require(project in allowed, 'PROJECT_NOT_ALLOWED', 403)
    context = resolve_context(project)
    require(context.project_id == project, 'PROJECT_ID_MISMATCH', 503)
    base = {'project': project, 'scope': 'host_configuration', 'execution_allowed': False}
    if action == 'project':
        fields = ('workflow', 'step_timeout', 'heartbeat', 'month_gate', 'max_tasks',
                  'stop_on_failure', 'max_runtime', 'project_agents')
        return {**base, 'source_mode': 'directory' if context.tasks_dir else 'jsonl',
                'configuration': {k: getattr(context, k) for k in fields},
                'steps': context.steps()}
    if action == 'catalog':
        from flowforge_agents import catalog
        names = sorted({'default'} | {
            p.stem for p in (config_home() / 'workflows').glob('*.json')})
        require(len(names) <= 100, 'CATALOG_TOO_LARGE', 502)
        workflows = [{'name': name, 'steps': pr.read_step_configs(context.named_workflow(name))}
                     for name in names]
        # The effective project workflow may be an explicit file rather than a named workflow.
        agents = catalog(context)
        require(len(agents) <= 100, 'CATALOG_TOO_LARGE', 502)
        fields = ('id', 'description', 'model', 'origin', 'mode')
        return {**base, 'workflows': workflows, 'project_steps': context.steps(), 'agents': [
            {**{k: bounded_text(a.get(k)) for k in fields},
             'issues': [bounded_text(i) for i in a['issues'][:20]],
             'issue_count': len(a['issues'])} for a in agents]}
    if action == 'doctor':
        from flowforge_cli import preflight
        report = preflight(context)
        return {**base, 'scope': 'inspection_container_preflight', 'ok': report['ok'],
                'issues': [bounded_text(i) for i in report['issues'][:20]],
                'issue_count': len(report['issues']), 'execution_verified': False}
    if action == 'sync-preview':
        from flowforge_sync import sync
        if context.tasks_dir is None:
            return {**base, 'applicable': False, 'reason': 'DIRECTORY_SOURCE_REQUIRED', 'applied': False}
        report = sync(context, dry_run=True)
        return {**base, 'applicable': True, 'applied': False, 'queue_total': report['queue_total'],
                'changes': {key: {'count': len(report[key]), 'task_ids': report[key][:50]}
                            for key in ('added', 'changed', 'missing', 'restored', 'unchanged')}}
    from flowforge_status import status
    # No private OpenCode session database is mounted in the reader container.
    report = status(context, db_path=Path('/nonexistent-inspection-session-db'))
    fields = ('id', 'status', 'title', 'stage', 'source_changed', 'source_missing',
              'attempt_id', 'last_run_log')
    rows = report['tasks']
    # Put active and failed work first, with a stable bounded window.
    rows = sorted(rows, key=lambda row: (row['status'] not in ('running', 'failed'), str(row['id'])))
    return {**base, 'scope': 'queue_records', 'counts': report['counts'],
            'task_total': len(rows), 'todo_count': report['queue_total'],
            'unknown_status_count': len(rows) - sum(report['counts'].values()),
            'tasks': [{k: bounded_text(row.get(k)) if k not in ('source_changed', 'source_missing')
                       else bool(row.get(k)) for k in fields} for row in rows[:50]],
            'truncated': len(rows) > 50, 'lock_observation': 'unavailable',
            'session_observation': 'unavailable'}


def read_in_child(action, project=None):
    command = [sys.executable, str(Path(__file__).resolve()), '--read', action]
    if project is not None:
        command.append(project)
    # No planning/Matrix/API secrets are inherited by the inspection subprocess.
    environment = {k: v for k, v in os.environ.items() if k in {
        'PATH', 'HOME', 'FLOWFORGE_RUNNER_DIR', 'FLOWFORGE_CONFIG_DIR',
        'FLOWFORGE_STATE_DIR', 'FLOWFORGE_READ_PROJECTS'}}
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        result = subprocess.run(command, env=environment, capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        raise InspectionError('INSPECTION_TIMEOUT', 504) from None
    require(result.returncode == 0, 'INSPECTION_FAILED', 502)
    require(len(result.stdout) <= MAX_OUTPUT, 'OUTPUT_TOO_LARGE', 502)
    value = json.loads(result.stdout)
    if value.get('success') is False:
        code = value.get('error')
        statuses = {'DIRECTORY_SOURCE_REQUIRED': 400, 'INVALID_INPUT': 400,
                    'PROJECT_NOT_ALLOWED': 403, 'PROJECT_ID_MISMATCH': 503,
                    'INVALID_PROJECT_ALLOWLIST': 503, 'CATALOG_TOO_LARGE': 502,
                    'OUTPUT_TOO_LARGE': 502}
        raise InspectionError(code if code in statuses else 'INSPECTION_FAILED', statuses.get(code, 502))
    return value


def create_server(address, token):
    require(isinstance(token, str) and len(token) >= 32, 'INVALID_TOKEN_CONFIG', 503)
    allowed_projects()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def handle_request(self):
            try:
                require(hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token),
                        'UNAUTHORIZED', 401)
                require(self.command == 'GET', 'METHOD_NOT_ALLOWED', 405)
                require('?' not in self.path and '%' not in self.path, 'INVALID_INPUT')
                if self.path == '/projects':
                    action, project = 'projects', None
                else:
                    match = re.fullmatch(r'/projects/([a-zA-Z0-9_-]{1,100})(?:/(catalog|status|doctor|sync-preview))?', self.path)
                    require(match is not None, 'NOT_FOUND', 404)
                    project, action = match[1], match[2] or 'project'
                    require(project in allowed_projects(), 'PROJECT_NOT_ALLOWED', 403)
                result = read_in_child(action, project)
                self.reply(200, result)
            except InspectionError as error:
                self.reply(error.status, {'success': False, 'error': error.code})
            except Exception:
                self.reply(502, {'success': False, 'error': 'INSPECTION_FAILED'})

        def reply(self, status, result):
            raw = json.dumps(result).encode()
            if len(raw) > MAX_OUTPUT:
                status, raw = 502, b'{"success":false,"error":"OUTPUT_TOO_LARGE"}'
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = handle_request

    return ThreadingHTTPServer(address, Handler)


if __name__ == '__main__':
    if len(sys.argv) in (3, 4) and sys.argv[1] == '--read':
        try:
            result = inspect(sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
            raw = json.dumps(result)
            require(len(raw.encode()) <= MAX_OUTPUT, 'OUTPUT_TOO_LARGE', 502)
            print(raw)
        except InspectionError as error:
            print(json.dumps({'success': False, 'error': error.code}))
        except Exception:
            print('{"success":false,"error":"INSPECTION_FAILED"}')
    else:
        create_server(('0.0.0.0', 8083), os.environ['FLOWFORGE_INSPECT_TOKEN']).serve_forever()
