"""Real FlowForge readers on disposable projects; HTTP and process boundaries included."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('flowforge_inspector', Path(__file__).with_name('inspector.py'))
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        runner = Path(__file__).resolve().parents[3] / 'apps/flow-forge-tui'
        if not (runner / 'flowforge_cli.py').exists():
            self.temp.cleanup()
            self.skipTest('Existing FlowForge project modules are unavailable')
        self.runner = runner
        self.config = self.root / 'config'
        (self.config / 'projects').mkdir(parents=True)
        (self.config / 'workflows').mkdir()
        self.library = self.config / 'library/agents'
        self.library.mkdir(parents=True)
        for agent in ('concept-plan', 'grounded-hard', 'execution-plan'):
            (self.library / f'{agent}.md').write_text('---\ndescription: Fixture agent\nmode: primary\nmodel: fixture/model\n---\nPRIVATE_PROMPT_BODY\n')
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.sources = self.root / 'inbox'
        (self.sources / 'one').mkdir(parents=True)
        (self.sources / 'one/task.md').write_text('# First task\nDo this.')
        self.queue = self.root / 'production.jsonl'
        self.queue.write_text(json.dumps({'id': 'old', 'task_file': str(self.sources / 'one/task.md'), 'status': 'running', 'session_id': 'PRIVATE_SESSION'}) + '\n')
        self.project = {'workspace': str(self.workspace), 'tasks_file': str(self.queue), 'opencode_bin': '/usr/bin/true'}
        (self.config / 'projects/mentory.json').write_text(json.dumps(self.project))
        (self.config / 'projects/hidden.json').write_text(json.dumps(self.project))
        (self.config / 'projects/directory.json').write_text(json.dumps({'workspace': str(self.workspace), 'tasks_dir': str(self.sources)}))
        (self.config / 'notifications.env').write_text('MATRIX_ACCESS_TOKEN=PRIVATE_NOTIFICATION_CREDENTIAL\n')
        self.environment = patch.dict(os.environ, {
            'FLOWFORGE_CONFIG_DIR': str(self.config), 'FLOWFORGE_STATE_DIR': str(self.root / 'state'),
            'FLOWFORGE_RUNNER_DIR': str(runner), 'FLOWFORGE_READ_PROJECTS': 'mentory,directory',
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def tree(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def test_real_readers_preserve_production_and_emit_only_bounded_metadata(self):
        before = self.tree()
        self.assertEqual(inspector.inspect('projects')['projects'], [
            {'project': 'directory', 'access': 'READ'}, {'project': 'mentory', 'access': 'READ'}])
        project = inspector.inspect('project', 'mentory')
        self.assertEqual(project['source_mode'], 'jsonl')
        self.assertEqual([s['id'] for s in project['steps']], ['concept', 'grounded', 'execution'])
        catalog = inspector.inspect('catalog', 'mentory')
        self.assertEqual({a['id'] for a in catalog['agents']}, {'concept-plan', 'grounded-hard', 'execution-plan'})
        self.assertFalse(catalog['execution_allowed'])
        self.assertNotIn('PRIVATE_PROMPT_BODY', json.dumps(catalog))
        self.assertNotIn('PRIVATE_NOTIFICATION_CREDENTIAL', json.dumps(project))
        status = inspector.inspect('status', 'mentory')
        self.assertEqual(status['counts']['running'], 1)
        self.assertEqual(status['tasks'][0]['status'], 'running')
        self.assertEqual(status['lock_observation'], 'unavailable')
        self.assertNotIn('PRIVATE_SESSION', json.dumps(status))
        doctor = inspector.inspect('doctor', 'mentory')
        self.assertTrue(doctor['ok'])
        self.assertFalse(doctor['execution_verified'])
        preview = inspector.inspect('sync-preview', 'directory')
        self.assertEqual(preview['changes']['added']['count'], 1)
        self.assertFalse(preview['applied'])
        self.assertEqual(self.tree(), before)
        self.assertFalse((self.root / 'state').exists())

    def test_rejects_unknown_projects_and_jsonl_sync_and_does_not_recover_running(self):
        before = self.tree()
        for name in ('hidden', '../mentory', '/tmp/project', 'mentory?apply=true'):
            with self.assertRaises(inspector.InspectionError):
                inspector.inspect('project', name)
        preview = inspector.inspect('sync-preview', 'mentory')
        self.assertFalse(preview['applicable'])
        self.assertEqual(preview['reason'], 'DIRECTORY_SOURCE_REQUIRED')
        inspector.inspect('status', 'mentory')
        self.assertEqual(json.loads(self.queue.read_text())['status'], 'running')
        self.assertEqual(before, self.tree())

    def test_status_window_and_preview_counts_are_explicit(self):
        self.queue.write_text(''.join(json.dumps({'id': f'task-{i:03}', 'task_file': str(self.sources / 'one/task.md'), 'status': 'done'}) + '\n' for i in range(60)))
        report = inspector.inspect('status', 'mentory')
        self.assertEqual(report['task_total'], 60)
        self.assertEqual(len(report['tasks']), 50)
        self.assertTrue(report['truncated'])
        for i in range(55):
            source = self.sources / f'extra-{i}'
            source.mkdir()
            (source / 'task.md').write_text('Task')
        report = inspector.inspect('sync-preview', 'directory')
        self.assertEqual(report['changes']['added']['count'], 56)
        self.assertEqual(len(report['changes']['added']['task_ids']), 50)

    def test_process_uses_only_fixed_read_command_and_removes_credentials(self):
        with patch.dict(os.environ, {'GLM_API_KEY': 'private', 'FLOWFORGE_TOKEN': 'private', 'FLOWFORGE_INSPECT_TOKEN': 'private', 'MATRIX_ACCESS_TOKEN': 'private'}), \
                patch.object(inspector.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'{"project":"mentory"}')) as run:
            inspector.read_in_child('doctor', 'mentory')
        args, kwargs = run.call_args
        self.assertEqual(args[0][-3:], ['--read', 'doctor', 'mentory'])
        self.assertFalse({'GLM_API_KEY', 'FLOWFORGE_TOKEN', 'FLOWFORGE_INSPECT_TOKEN', 'MATRIX_ACCESS_TOKEN'} & kwargs['env'].keys())
        self.assertEqual(kwargs['timeout'], 20)
        with patch.object(inspector.subprocess, 'run', side_effect=subprocess.TimeoutExpired('read', 20)):
            with self.assertRaises(inspector.InspectionError) as error:
                inspector.read_in_child('status', 'mentory')
        self.assertEqual(error.exception.code, 'INSPECTION_TIMEOUT')

    def test_exact_mounted_module_set_works_without_production_env_or_private_notifications(self):
        compose = Path(__file__).parents[1] / 'hermes/docker-compose.yml'
        service = compose.read_text().split('  flowforge-inspect:\n')[1].split('  homelab-broker:\n')[0]
        import re
        modules = re.findall(r'/([^/:]+):/source/flowforge/[^:]+:ro', service)
        mounted = self.root / 'mounted'
        mounted.mkdir()
        for name in modules:
            shutil.copyfile(self.runner / name, mounted / name)
        (self.config / 'notifications.env').unlink()
        before = self.tree()
        with patch.dict(os.environ, {'FLOWFORGE_RUNNER_DIR': str(mounted), 'PROJECT_DIR': '/never/production', 'TASKS_FILE': '/never/production.jsonl'}):
            for action in ('projects', 'project', 'catalog', 'status', 'doctor'):
                report = inspector.read_in_child(action, None if action == 'projects' else 'mentory')
                self.assertNotEqual(report.get('success'), False)
            report = inspector.read_in_child('sync-preview', 'directory')
            self.assertFalse(report['applied'])
        self.assertEqual(before, self.tree())

    def test_authenticated_get_only_http_and_safe_errors(self):
        token = 'a' * 32
        server = inspector.create_server(('127.0.0.1', 0), token)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def request(path, method='GET', credential=token):
            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}' + path, method=method,
                                         headers={'Authorization': 'Bearer ' + credential})
            try:
                with urllib.request.urlopen(req) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                return error.code, json.load(error)
        before = self.tree()
        self.assertEqual(request('/projects')[0], 200)
        self.assertEqual(request('/projects/mentory/catalog')[0], 200)
        self.assertEqual(request('/projects', credential='invalid')[0], 401)
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            self.assertEqual(request('/projects/mentory', method=method)[0], 405)
        self.assertEqual(request('/projects/hidden')[0], 403)
        for path in ('/projects?apply=true', '/projects/mentory?workspace=/tmp', '/projects/%2e%2e'):
            self.assertEqual(request(path)[0], 400)
        for path in ('/run', '/projects/mentory/reset', '/projects/mentory/sync'):
            self.assertEqual(request(path)[0], 404)
        code, result = request('/projects/mentory/sync-preview')
        self.assertEqual(code, 200)
        self.assertFalse(result['applicable'])
        with patch.object(inspector, 'read_in_child', side_effect=ValueError('PRIVATE_FAILURE')):
            status, result = request('/projects')
        self.assertEqual((status, result), (502, {'success': False, 'error': 'INSPECTION_FAILED'}))
        self.assertEqual(before, self.tree())


if __name__ == '__main__':
    unittest.main()
