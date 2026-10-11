"""Regression checks for alert decisions; does not stop production services."""
import collections
import unittest
from unittest.mock import patch
import json
from pathlib import Path
import tempfile
import urllib.error
import io
import os

import monitor


class DatabaseDumpHealth(unittest.TestCase):
    def test_missing_empty_fresh_stale_and_future_dump(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synapse.dump'
            config = {'path': str(path), 'maximum_age_hours': 2}
            self.assertEqual(monitor.database_dump_status(config, 10000)['level'], 'critical')
            path.touch()
            self.assertEqual(monitor.database_dump_status(config, 10000)['level'], 'critical')
            path.write_bytes(b'archive')
            for modified, expected in [(9900, 'ok'), (1000, 'critical'), (11000, 'critical')]:
                os.utime(path, (modified, modified))
                self.assertEqual(monitor.database_dump_status(config, 10000)['level'], expected)


class MatrixDelivery(unittest.TestCase):
    def test_failed_delivery_preserves_queue_and_transaction_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            state = {'pending': [
                {'transaction_id': 'stable-id', 'body': 'CRITICAL test'},
                {'transaction_id': 'recovery-id', 'body': 'RECOVERED test'}]}
            monitor.save_state(path, state)
            with patch.object(monitor, 'send_matrix', side_effect=TimeoutError):
                with self.assertRaises(TimeoutError):
                    monitor.deliver_pending(state, path, {})
            self.assertEqual(json.loads(path.read_text()), state)
            with patch.object(monitor, 'send_matrix') as send:
                monitor.deliver_pending(state, path, {})
            self.assertEqual([call.args[1]['transaction_id'] for call in send.call_args_list],
                             ['stable-id', 'recovery-id'])
            self.assertEqual(json.loads(path.read_text())['pending'], [])

    def test_encrypted_room_blocks_plaintext(self):
        with patch.object(monitor, 'matrix_request', return_value={}) as request:
            with self.assertRaises(RuntimeError):
                monitor.send_matrix({'room_id': '!room:server'}, {'transaction_id': 'id', 'body': 'test'})
            self.assertEqual(request.call_count, 1)

    def test_unencrypted_room_sends_with_stable_transaction(self):
        missing = urllib.error.HTTPError('http://localhost', 404, 'Not found', {},
                                         io.BytesIO(b'{"errcode":"M_NOT_FOUND"}'))
        with patch.object(monitor, 'matrix_request', side_effect=[missing, {'event_id': '$event'}]) as request:
            monitor.send_matrix({'room_id': '!room:server'}, {'transaction_id': 'stable-id', 'body': 'test'})
            self.assertEqual(request.call_args.args[1], 'PUT')
            self.assertTrue(request.call_args.args[2].endswith('/stable-id'))

    def test_unexpected_404_does_not_send(self):
        missing = urllib.error.HTTPError('http://localhost', 404, 'Not found', {},
                                         io.BytesIO(b'{"errcode":"M_UNKNOWN"}'))
        with patch.object(monitor, 'matrix_request', side_effect=missing) as request:
            with self.assertRaises(urllib.error.HTTPError):
                monitor.send_matrix({'room_id': '!room:server'}, {})
            self.assertEqual(request.call_count, 1)


class BackupAlerts(unittest.TestCase):
    def operation(self, status, start, end=None, **extra):
        return {'operationBackup': {}, 'status': status,
                'unixTimeStartMs': str(start * 1000),
                'unixTimeEndMs': str((end or start) * 1000), **extra}

    def test_future_scheduled_run_does_not_hide_actual_failure(self):
        operations = [self.operation('STATUS_SUCCESS', 100),
                      self.operation('STATUS_ERROR', 200),
                      self.operation('STATUS_PENDING', 10000)]
        result = monitor.backup_status(operations, {'maximum_age_hours': 36}, 300)
        self.assertEqual(result['level'], 'critical')
        self.assertIn('STATUS_ERROR', result['message'])

    def test_new_success_recovers_from_previous_failure(self):
        operations = [self.operation('STATUS_ERROR', 100),
                      self.operation('STATUS_SUCCESS', 200)]
        self.assertEqual(monitor.backup_status(operations, {'maximum_age_hours': 36}, 300)['level'], 'ok')

    def test_dry_run_does_not_count_as_a_recoverable_backup(self):
        operation = self.operation('STATUS_SUCCESS', 200, operationBackup={'dryRun': True})
        self.assertEqual(monitor.backup_status([operation], {'maximum_age_hours': 36}, 300)['level'], 'critical')

    def test_stale_backup_alerts_even_if_latest_run_succeeded(self):
        result = monitor.backup_status([self.operation('STATUS_SUCCESS', 100)],
                                       {'maximum_age_hours': 36}, 37 * 3600)
        self.assertEqual(result['level'], 'critical')
        self.assertIn('hours old', result['message'])


class AlertLifecycle(unittest.TestCase):
    def test_no_duplicate_alert_then_reminder_and_recovery(self):
        problem = {'backup': {'level': 'critical', 'message': 'Backup failed'}}
        messages, first = monitor.transitions({}, problem, 1000, 600)
        self.assertEqual(len(messages), 1)
        messages, second = monitor.transitions(first, problem, 1300, 600)
        self.assertEqual(messages, [])
        messages, third = monitor.transitions(second, problem, 1600, 600)
        self.assertEqual(len(messages), 1)
        messages, _ = monitor.transitions(third, {'backup': {'level': 'ok', 'message': 'Backup succeeded'}}, 1700, 600)
        self.assertEqual(len(messages), 1)
        self.assertIn('RECOVERED', messages[0])

    def test_severity_escalation_alerts_before_reminder(self):
        _, first = monitor.transitions({}, {'disk': {'level': 'warning', 'message': '85%'}}, 1000, 600)
        messages, _ = monitor.transitions(first, {'disk': {'level': 'critical', 'message': '95%'}}, 1001, 600)
        self.assertEqual(len(messages), 1)
        self.assertIn('CRITICAL', messages[0])

    def test_healthy_first_run_does_not_send_recovery_alerts(self):
        messages, _ = monitor.transitions({}, {'disk': {'level': 'ok', 'message': 'Healthy'}}, 1000, 600)
        self.assertEqual(messages, [])

    def test_low_free_space_alerts_on_large_disks_below_percent_threshold(self):
        usage = collections.namedtuple('Usage', 'total used free')(100 * 1024**3, 70 * 1024**3, 1024**3)
        result = monitor.disk_status({'path': '/', 'critical_percent': 95, 'warning_percent': 85, 'minimum_free_gib': 2}, usage)
        self.assertEqual(result['level'], 'critical')


if __name__ == '__main__':
    unittest.main()
