import hashlib
import importlib.util
import json
import os
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
        agents = self.source / '.opencode/agents'
        agents.mkdir(parents=True)
        for name in ('concept-plan', 'grounded-hard'):
            (agents / (name + '.md')).write_text('---\nmode: primary\n---\nExisting planning prompt\n')
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
            def read_step_configs():
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
    def test_existing_runner_executes_two_planning_steps_against_private_queue(self):
        import sys
        from types import SimpleNamespace
        runner_path = Path(__file__).resolve().parents[3] / 'apps/flow-forge-tui/pipeline_runner.py'
        if not runner_path.exists():
            self.skipTest('Existing FlowForge checkout is not available')
        configs = [{'id': 'concept', 'label': 'Business plan', 'agent': 'concept-plan'}, {'id': 'grounded', 'label': 'Technical plan', 'agent': 'grounded-hard'}, {'id': 'execution', 'label': 'Execution', 'agent': 'execution-plan'}]
        folder = self.root / 'live-runner-job'
        folder.mkdir()
        project, task_dir = module.prepare_job(self.payload['input'], {'task_file': str(self.task)}, SimpleNamespace(read_step_configs=lambda: configs, task_agents=lambda task, configs: {item['id']: item['agent'] for item in configs}), folder)
        module.write_json(folder / 'status.json', {'task_id': 'test', 'status': 'RUNNING'})
        source_before = self.task.read_bytes()
        calls = []
        with patch.dict(os.environ, {'PROJECT_DIR': str(project), 'TASKS_FILE': str(folder / 'tasks.jsonl'), 'FLOWFORGE_RUNS_DIR': str(folder / 'logs')}):
            runner_spec = importlib.util.spec_from_file_location('isolated_flowforge_test_runner', runner_path)
            pr = importlib.util.module_from_spec(runner_spec)
            sys.modules[runner_spec.name] = pr
            runner_spec.loader.exec_module(pr)
            def planner(**kwargs):
                calls.append(kwargs['agent'])
                name = 'concept-plan.md' if kwargs['agent'] == 'concept-plan' else 'grounded-plan.md'
                (kwargs['files'][0].parent / name).write_text('Existing runner output')
                return 0, '', 'isolated-test-session', False
            with patch.object(module, 'runner', return_value=pr), patch.object(pr, 'run_opencode_step_stream', side_effect=planner):
                module.worker(folder)
        self.assertEqual(calls, ['concept-plan', 'grounded-hard'])
        self.assertEqual(json.loads((folder / 'status.json').read_text())['status'], 'DONE')
        self.assertEqual(self.task.read_bytes(), source_before)

    def test_oversized_source_is_omitted_with_an_explicit_manifest(self):
        from types import SimpleNamespace
        large = self.source / 'large-binary.dat'
        with large.open('wb') as output:
            output.truncate(16777217)
        subprocess.run(['git', '-C', str(self.source), 'add', 'large-binary.dat'], check=True)
        configs = [{'id':'concept','agent':'concept-plan'}, {'id':'grounded','agent':'grounded-hard'}]
        pr = SimpleNamespace(read_step_configs=lambda: configs, task_agents=lambda task, configs: {item['id']:item['agent'] for item in configs})
        folder = self.root / 'large-job'
        folder.mkdir()
        project, _ = module.prepare_job(self.payload['input'], {'task_file':str(self.task)}, pr, folder)
        self.assertFalse((project / 'large-binary.dat').exists())
        self.assertIn('large-binary.dat', (project / 'HERMES_SNAPSHOT_LIMITS.md').read_text())


if __name__ == '__main__':
    unittest.main()
