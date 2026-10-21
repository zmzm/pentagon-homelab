"""Verify recovery result publication and alert decisions without Docker or messages."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import monitor
import recovery_test


class RecoveryPublication(unittest.TestCase):
    def test_failure_and_interruption_preserve_last_success_without_secrets(self):
        for error in (RuntimeError('sensitive fixture'), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                recovery_test.save_status(path, {'last_success_at': 100})
                with patch.object(recovery_test.time, 'time', side_effect=[200, 210]):
                    def fail():
                        running = json.loads((path / 'status.json').read_text())
                        self.assertEqual(running['status'], 'running')
                        raise error
                    self.assertFalse(recovery_test.verify_and_record(path, fail))
                result = json.loads((path / 'status.json').read_text())
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['last_success_at'], 100)
                self.assertNotIn('sensitive', json.dumps(result))
                self.assertEqual((path / 'status.json').stat().st_mode & 0o777, 0o600)
                self.assertFalse((path / 'status.json.partial').exists())

    def test_success_is_only_published_after_verifier_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            def verify():
                self.assertEqual(json.loads((path / 'status.json').read_text())['status'], 'running')
            with patch.object(recovery_test.time, 'time', side_effect=[200, 210]):
                self.assertTrue(recovery_test.verify_and_record(path, verify))
            result = json.loads((path / 'status.json').read_text())
            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['last_success_at'], 210)


class RecoveryHealth(unittest.TestCase):
    def test_missing_failed_stale_future_and_stuck_results_alert(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            config = {'status_file': str(path), 'maximum_age_hours': 192,
                      'maximum_running_minutes': 35}
            now = 1000000
            self.assertEqual(monitor.recovery_status(config, now)['level'], 'critical')
            cases = [
                ({'status': 'success', 'started_at': now-100, 'last_success_at': now-10}, 'ok'),
                ({'status': 'failed', 'started_at': now-100, 'last_success_at': now-10}, 'critical'),
                ({'status': 'success', 'started_at': 0, 'last_success_at': 0}, 'critical'),
                ({'status': 'success', 'started_at': now+600, 'last_success_at': now}, 'critical'),
                ({'status': 'success', 'started_at': now, 'last_success_at': now+600}, 'critical'),
                ({'status': 'running', 'started_at': now-60, 'last_success_at': None}, 'ok'),
                ({'status': 'running', 'started_at': now-2200, 'last_success_at': now-10}, 'critical'),
                ({'status': 'running', 'started_at': now-60, 'last_success_at': 0}, 'critical'),
            ]
            for result, expected in cases:
                with self.subTest(result=result):
                    path.write_text(json.dumps(result))
                    self.assertEqual(monitor.recovery_status(config, now)['level'], expected)


if __name__ == '__main__':
    unittest.main()
