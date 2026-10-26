import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('flowforge_adapter', Path(__file__).with_name('adapter.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.agents = self.root / 'central-agents'
        self.agents.mkdir(parents=True)
        for name in ('concept-plan', 'grounded-hard'):
            (self.agents / (name + '.md')).write_text('---\ndescription: Planning fixture\nmode: primary\n---\nExisting planning prompt\n')
        self.configs = [
            {'id': 'concept', 'label': 'Business plan', 'agent': 'concept-plan', 'model': 'fixture/concept'},
            {'id': 'grounded', 'label': 'Technical plan', 'agent': 'grounded-hard', 'model': 'fixture/grounded'},
            {'id': 'execution', 'label': 'Execution', 'agent': 'execution-plan', 'model': 'fixture/execution'},
        ]
        self.steps = self.root / 'source-steps.json'
        self.steps.write_text(json.dumps({'steps': self.configs}))
        self.agent_patch = patch.object(module, 'PLANNING_AGENTS', self.agents)
        self.agent_patch.start()
        self.steps_patch = patch.object(module, 'STEPS', self.steps)
        self.steps_patch.start()
        (self.source / 'app.py').write_text('original = True\n')
        (self.source / '.env').write_text('SECRET=never-copy\n')
        self.task = self.source / '.opencode/tasks/test/task.md'
        self.task.parent.mkdir(parents=True)
        self.task.write_text('# Existing task\nAnalyze this scope.\n')
        subprocess.run(['git', 'init', '-q', str(self.source)], check=True)
        subprocess.run(['git', '-C', str(self.source), 'add', '.'], check=True)
        self.payload = {'workflow': 'task-analysis', 'input': {'project': 'mentory', 'task_id': 'test', 'task_sha256': hashlib.sha256(self.task.read_bytes()).hexdigest(), 'context': 'Retrieved coding guidance'}}
        self.env = patch.dict(os.environ, {'FLOWFORGE_SOURCE_PROJECT': str(self.source)})
        self.env.start()
        self.project = patch.object(module, 'PROJECT', self.source)
        self.project.start()

    def tearDown(self):
        self.steps_patch.stop()
        self.agent_patch.stop()
        self.project.stop()
        self.env.stop()
        for path in self.root.rglob('*'):
            if path.is_dir():
                path.chmod(0o700)
        self.temporary.cleanup()

    def test_validation_rejects_execution_unknown_projects_and_changed_inputs(self):
        for changes in ({'workflow': 'execution'}, {'input': {'project': 'other'}}, {'input': {**self.payload['input'], 'command': 'rm -rf'}}, {'input': {**self.payload['input'], 'context': 'x' * 5001}}):
            with self.assertRaises(module.Failure):
                module.validate_run({**self.payload, **changes})
        self.assertEqual(module.validate_run(self.payload)['task_id'], 'test')

    def test_preparation_reuses_only_planning_steps_and_preserves_source(self):
        class Runner:
            task_agents = staticmethod(lambda task, configs: {item['id']: item['agent'] for item in configs})
            @staticmethod
            def read_step_configs(path):
                return [{'id': 'concept', 'agent': 'concept-plan'}, {'id': 'grounded', 'agent': 'grounded-hard'}, {'id': 'execution', 'agent': 'execution-plan'}]
        folder = self.root / 'job'
        folder.mkdir()
        source_before = self.task.read_bytes()
        project, task_dir = module.prepare_job(self.payload['input'], {'task_file': str(self.task)}, Runner(), folder)
        task = json.loads((folder / 'tasks.jsonl').read_text())
        self.assertEqual(task['run_steps'], ['concept', 'grounded'])
        self.assertEqual([step['id'] for step in json.loads((folder / 'steps.json').read_text())['steps']], ['concept', 'grounded'])
        self.assertEqual(self.task.read_bytes(), source_before)
        self.assertFalse((project / '.env').exists())
        self.assertFalse((project / '.opencode/agents/execution-plan.md').exists())
        self.assertEqual((project / 'app.py').stat().st_mode & 0o222, 0)
        self.assertIn('Retrieved coding guidance', (task_dir / 'task.md').read_text())

    def test_task_hash_is_checked_before_snapshot_or_execution(self):
        folder = self.root / 'job'
        folder.mkdir()
        self.task.write_text('Changed after approval')
        with self.assertRaisesRegex(module.Failure, '') as failure:
            module.prepare_job(self.payload['input'], {'task_file': str(self.task)}, None, folder)
        self.assertEqual(failure.exception.code, 'TASK_CHANGED_REVIEW_AGAIN')
        self.assertFalse((folder / 'project').exists())

    def test_paths_outside_project_and_symlink_escapes_are_rejected(self):
        outside = self.root / 'outside.md'
        outside.write_text('not a project task')
        with self.assertRaises(module.Failure):
            module.task_source({'task_file': str(outside)})
        link = self.source / 'escape.md'
        link.symlink_to(outside)
        with self.assertRaises(module.Failure):
            module.task_source({'task_file': str(link)})

    def test_restart_marks_unfinished_runs_failed_without_replaying(self):
        job = self.root / 'state/test'
        job.mkdir(parents=True)
        module.write_json(job / 'status.json', {'status': 'RUNNING'})
        module.Adapter(None, self.root / 'state')
        record = json.loads((job / 'status.json').read_text())
        self.assertEqual(record['status'], 'FAILED')
        self.assertEqual(record['error'], 'INTERRUPTED_REVIEW_REQUIRED')
    def runner_path(self):
        runner_path = Path(__file__).resolve().parents[3] / 'apps/flow-forge-tui/pipeline_runner.py'
        if not runner_path.exists():
            self.skipTest('Existing FlowForge checkout is not available')
        return runner_path

    def load_runner(self):
        with patch.object(module, 'RUNNER_DIR', self.runner_path().parent):
            return module.runner()

    def prepare_fixture(self, name, pr):
        folder = self.root / name
        folder.mkdir()
        project, task_dir = module.prepare_job(self.payload['input'], {'task_file': str(self.task)}, pr, folder)
        module.write_json(folder / 'status.json', {'task_id': 'test', 'status': 'RUNNING'})
        return folder, project, task_dir

    def test_existing_runner_executes_two_private_steps_with_explicit_timeout(self):
        pr = self.load_runner()
        folder, project, task_dir = self.prepare_fixture('live-runner-job', pr)
        source_before = self.task.read_bytes()
        source_steps_before = self.steps.read_bytes()
        calls = []
        def planner(**kwargs):
            context = kwargs['context']
            calls.append((kwargs['agent'], kwargs['model']))
            self.assertEqual(context.workspace, project.resolve())
            self.assertEqual(context.tasks_file, (folder / 'tasks.jsonl').resolve())
            self.assertEqual(context.runs_dir, (folder / 'logs').resolve())
            self.assertEqual(context.step_timeout, 900)
            permissions = json.loads(os.environ['OPENCODE_CONFIG_CONTENT'])
            self.assertFalse(permissions['mcp']['serena']['enabled'])
            self.assertEqual(permissions['agent'][kwargs['agent']]['permission']['bash']['*'], 'deny')
            self.assertNotIn('*', permissions['agent'][kwargs['agent']]['permission'])
            name = 'concept-plan.md' if kwargs['agent'] == 'concept-plan' else 'grounded-plan.md'
            (kwargs['files'][0].parent / name).write_text('Existing runner output')
            return 0, '', 'isolated-test-session', False
        with patch.dict(os.environ, {'PROJECT_DIR': '/never/use/production', 'TASKS_FILE': '/never/use/production.jsonl', 'FLOWFORGE_STEP_TIMEOUT_SECONDS': '1'}), patch.object(pr, 'run_opencode_step_stream', side_effect=planner), patch.dict(os.environ):
            module.worker(folder)
            self.assertEqual(os.environ['PROJECT_DIR'], '/never/use/production')
            self.assertEqual(os.environ['TASKS_FILE'], '/never/use/production.jsonl')
        self.assertEqual(calls, [('concept-plan', 'fixture/concept'), ('grounded-hard', 'fixture/grounded')])
        result = json.loads((folder / 'status.json').read_text())
        self.assertEqual(result['status'], 'DONE')
        self.assertEqual(set(result['outputs']), {'concept-plan.md', 'grounded-plan.md'})
        self.assertEqual(self.task.read_bytes(), source_before)
        self.assertEqual(self.steps.read_bytes(), source_steps_before)

    def test_oversized_source_is_omitted_with_an_explicit_manifest(self):
        from types import SimpleNamespace
        large = self.source / 'large-binary.dat'
        with large.open('wb') as output:
            output.truncate(16777217)
        subprocess.run(['git', '-C', str(self.source), 'add', 'large-binary.dat'], check=True)
        configs = [{'id':'concept','agent':'concept-plan'}, {'id':'grounded','agent':'grounded-hard'}]
        pr = SimpleNamespace(read_step_configs=lambda path: configs, task_agents=lambda task, configs: {item['id']:item['agent'] for item in configs})
        folder = self.root / 'large-job'
        folder.mkdir()
        project, _ = module.prepare_job(self.payload['input'], {'task_file':str(self.task)}, pr, folder)
        self.assertFalse((project / 'large-binary.dat').exists())
        self.assertIn('large-binary.dat', (project / 'HERMES_SNAPSHOT_LIMITS.md').read_text())


    def test_central_agent_is_required_even_when_project_copy_exists(self):
        legacy = self.source / '.opencode/agents'
        legacy.mkdir(parents=True)
        for name in ('concept-plan', 'grounded-hard'):
            (legacy / (name + '.md')).write_text('Stale project definition')
        pr = self.load_runner()
        folder, project, _ = self.prepare_fixture('central-source', pr)
        self.assertEqual((project / '.opencode/agents/concept-plan.md').read_bytes(), (self.agents / 'concept-plan.md').read_bytes())
        (self.agents / 'grounded-hard.md').unlink()
        another = self.root / 'missing-agent'; another.mkdir()
        with self.assertRaises(module.Failure) as failure:
            module.prepare_job(self.payload['input'], {'task_file': str(self.task)}, pr, another)
        self.assertEqual(failure.exception.code, 'PLANNING_AGENT_NOT_FOUND')

    def test_worker_rejects_execution_and_missing_private_workflow(self):
        pr = self.load_runner()
        for change in ('extra-step', 'extra-run-step', 'task-workflow', 'missing-config'):
            folder, _, _ = self.prepare_fixture(change, pr)
            if change == 'extra-step':
                module.write_json(folder / 'steps.json', {'steps': self.configs})
            elif change == 'missing-config':
                (folder / 'steps.json').unlink()
            else:
                task = json.loads((folder / 'tasks.jsonl').read_text())
                task.update({'run_steps': ['concept', 'grounded', 'execution']} if change == 'extra-run-step' else {'workflow': 'default'})
                module.write_json(folder / 'tasks.jsonl', task)
            with self.subTest(change=change), patch.dict(os.environ), patch.object(pr, 'run_opencode_step_stream') as process:
                module.worker(folder)
                process.assert_not_called()
                result = json.loads((folder / 'status.json').read_text())
                self.assertEqual(result['status'], 'FAILED')
                self.assertEqual(result['error'], 'PLANNING_STEPS_NOT_CONFIGURED')

    def test_worker_observes_canonical_execution_locks(self):
        pr = self.load_runner()
        from flowforge_storage import acquire_execution
        folder, _, _ = self.prepare_fixture('locked', pr)
        lock = acquire_execution(module.planning_context(folder, pr))
        self.assertIsNotNone(lock)
        try:
            with patch.dict(os.environ), patch.object(pr, 'run_opencode_step_stream') as process:
                module.worker(folder)
                process.assert_not_called()
                result = json.loads((folder / 'status.json').read_text())
                self.assertEqual(result['status'], 'FAILED')
                self.assertEqual(result['error'], 'WORKFLOW_BUSY')
        finally:
            lock.close()

    def test_model_failure_remains_failed_without_touching_source(self):
        pr = self.load_runner()
        folder, _, _ = self.prepare_fixture('provider-failure', pr)
        before = self.task.read_bytes()
        with patch.dict(os.environ), patch.object(pr, 'run_opencode_step_stream', return_value=(1, '', None, False)) as process:
            module.worker(folder)
        self.assertEqual(process.call_count, 1)
        result = json.loads((folder / 'status.json').read_text())
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['error'], 'PLANNING_PIPELINE_FAILED')
        self.assertEqual(self.task.read_bytes(), before)

    def test_compose_mounted_modules_run_two_isolated_jobs_with_fake_processes(self):
        runner_dir = self.runner_path().parent
        compose = Path(__file__).resolve().parents[1] / 'hermes/docker-compose.yml'
        mounts = re.findall(r'\$\{FLOWFORGE_PATH[^}]*\}/([^:]+):/source/flowforge/([^:]+):ro', compose.read_text())
        mounted = self.root / 'mounted-runner'; mounted.mkdir()
        for source, target in mounts:
            shutil.copyfile(runner_dir / source, mounted / target)
        pr = self.load_runner()
        jobs = [self.prepare_fixture(name, pr)[0] for name in ('first', 'second')]
        driver = self.root / 'driver.py'
        driver.write_text(r'''
import importlib.util,json,os,sys
from pathlib import Path
sys.path.insert(0,os.environ['MOUNTED_RUNNER'])
spec=importlib.util.spec_from_file_location('adapter',os.environ['ADAPTER_SOURCE'])
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
adapter.RUNNER_DIR=Path(os.environ['MOUNTED_RUNNER'])
pr=adapter.runner()
calls=[]
def fake(**kwargs):
    context=kwargs['context']
    assert context.step_timeout==900
    assert context.legacy
    assert str(context.workspace).startswith(os.environ['TEST_ROOT'])
    permission=json.loads(os.environ['OPENCODE_CONFIG_CONTENT'])
    assert permission['mcp']['serena']['enabled'] is False
    name='concept-plan.md' if kwargs['agent']=='concept-plan' else 'grounded-plan.md'
    assert kwargs['agent'] in ('concept-plan','grounded-hard')
    (kwargs['files'][0].parent/name).write_text('Mock process result')
    calls.append({'workspace':str(context.workspace),'queue':str(context.tasks_file),'timeout':context.step_timeout,'agent':kwargs['agent'],'model':kwargs['model']})
    return 0,'','fake-session',False
pr.run_opencode_step_stream=fake
for folder in json.loads(os.environ['JOBS']):
    adapter.worker(Path(folder))
    record=json.loads((Path(folder)/'status.json').read_text())
    assert record['status']=='DONE',record
assert os.environ['PROJECT_DIR']=='/forbidden-production-workspace'
assert os.environ['TASKS_FILE']=='/forbidden-production-queue'
print(json.dumps(calls))
''')
        environment = {
            'PATH': os.environ['PATH'], 'HOME': str(self.root / 'home'),
            'PYTHONDONTWRITEBYTECODE': '1', 'MOUNTED_RUNNER': str(mounted),
            'ADAPTER_SOURCE': str(Path(module.__file__).resolve()),
            'TEST_ROOT': str(self.root), 'JOBS': json.dumps([str(job) for job in jobs]),
            'PROJECT_DIR': '/forbidden-production-workspace', 'TASKS_FILE': '/forbidden-production-queue',
            'MATRIX_ENABLED': 'false',
        }
        before = self.task.read_bytes()
        completed = subprocess.run([sys.executable, str(driver)], cwd=self.root, env=environment,
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        calls = json.loads(completed.stdout)
        self.assertEqual([call['agent'] for call in calls], ['concept-plan', 'grounded-hard'] * 2)
        self.assertEqual({call['timeout'] for call in calls}, {900})
        self.assertEqual(len({call['workspace'] for call in calls}), 2)
        self.assertEqual(len({call['queue'] for call in calls}), 2)
        self.assertEqual([call['model'] for call in calls], ['fixture/concept', 'fixture/grounded'] * 2)
        self.assertEqual(self.task.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
