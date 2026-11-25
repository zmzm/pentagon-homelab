"""Offline delivery/recovery checks. No real Telegram, Matrix or Docker calls."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import monitor
import monitor_telegram as telegram
import verify_monitor_telegram as verify


CONFIG = {'enabled': True, 'credentials_file': 'telegram-private.json',
          'bot_id': '123456', 'chat_id': '654321'}
TOKEN = '123456:' + 'fixture_' * 4


class TelegramTransport(unittest.TestCase):
    def call(self, response, http_status=200):
        if isinstance(response, Exception):
            effect = response
        else:
            body = io.BytesIO(json.dumps(response).encode())
            effect = body if http_status == 200 else urllib.error.HTTPError(
                'https://api.telegram.org/bot' + TOKEN, http_status, 'private-error', {}, body)
        with patch.object(telegram.urllib.request, 'build_opener') as build:
            if isinstance(effect, Exception):
                build.return_value.open.side_effect = effect
            else:
                build.return_value.open.return_value = effect
            result = telegram.send(TOKEN, CONFIG['chat_id'], 'safe summary')
        return result, build.return_value.open.call_args.args[0]

    def test_confirmed_send_has_fixed_endpoint_destination_and_no_formatting(self):
        result, request = self.call({'ok': True, 'result': {
            'message_id': 7, 'chat': {'id': 654321, 'type': 'private'}}})
        self.assertEqual(result, ('confirmed', 0))
        self.assertEqual(request.full_url, 'https://api.telegram.org/bot' + TOKEN + '/sendMessage')
        self.assertEqual(json.loads(request.data), {
            'chat_id': '654321', 'text': 'safe summary',
            'link_preview_options': {'is_disabled': True}, 'protect_content': True})

    def test_only_explicit_rate_rejection_is_retryable(self):
        for status in (200, 429):
            result, _ = self.call({'ok': False, 'error_code': 429,
                                  'parameters': {'retry_after': 900}}, status)
            self.assertEqual(result, ('rate_limited', 900))
        for status in (400, 401, 403):
            result, _ = self.call({'ok': False, 'error_code': status}, status)
            self.assertEqual(result, ('blocked', 0))

    def test_timeout_redirect_server_error_and_malformed_results_are_uncertain(self):
        fixtures = [(TimeoutError(TOKEN), 200), ({'ok': False, 'error_code': 500}, 500),
                    ({'ok': False, 'error_code': 408}, 408), ({}, 302), ([], 200),
                    ({'ok': True, 'result': None}, 200),
                    ({'ok': True, 'result': {'message_id': 1, 'chat': {'id': 999}}}, 200),
                    ({'ok': False, 'error_code': 429, 'parameters': {'retry_after': True}}, 429)]
        for response, status in fixtures:
            with self.subTest(response=response, status=status):
                self.assertEqual(self.call(response, status)[0], ('uncertain', 0))
        self.assertIsNone(telegram.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test'))


class TelegramState(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'telegram.json'
        self.state = telegram.load_state(self.path, CONFIG)
        telegram.enqueue(self.state, ['CRITICAL [disk] PRIVATE-TEXT ' + TOKEN], {}, 1000)
        monitor.save_state(self.path, self.state)

    def deliver(self, outcome, now=1000, state=None):
        with patch.object(telegram, 'send', return_value=outcome) as send:
            telegram.deliver(state or self.state, self.path, TOKEN, now, monitor.save_state)
        return send

    def test_projection_omits_secrets_urls_paths_and_arbitrary_keys(self):
        messages = [f'CRITICAL [{key}] {TOKEN} https://private.test /private/path password=hunter2'
                    for key in ('disk', 'container:PRIVATE-NAME', 'http:PRIVATE-NAME', 'PRIVATE-NAME')]
        telegram.enqueue(self.state, messages, {'disk': {'level': 'critical',
                                                       'last_notified': 5, 'message': TOKEN}}, 1000)
        text = telegram.message_text(self.state['pending'][-1])
        for secret in (TOKEN, 'PRIVATE', 'https:', '/private', 'hunter2'):
            self.assertNotIn(secret, text)
        self.assertNotIn(TOKEN, json.dumps(self.state))
        self.assertLess(len(text), 4096)
        self.assertTrue(telegram.valid_summary(self.state['pending'][-1]['summary']))

    def test_claim_precedes_send_and_success_is_not_repeated(self):
        def send(*args):
            stored = json.loads(self.path.read_text())['pending'][0]
            self.assertEqual(stored['status'], 'sending')
            self.assertEqual(stored['attempts'], 1)
            return 'confirmed', 0
        with patch.object(telegram, 'send', side_effect=send) as dispatch:
            telegram.deliver(self.state, self.path, TOKEN, 1000, monitor.save_state)
            telegram.deliver(telegram.load_state(self.path, CONFIG), self.path, TOKEN, 1001, monitor.save_state)
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(json.loads(self.path.read_text())['pending'], [])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_failed_claim_does_not_dispatch(self):
        with patch.object(telegram, 'send') as send:
            with self.assertRaises(OSError):
                telegram.deliver(self.state, self.path, TOKEN, 1000,
                                 lambda *args: (_ for _ in ()).throw(OSError()))
        send.assert_not_called()

    def test_lost_success_persistence_becomes_uncertain_after_restart(self):
        def save(path, state):
            if not state['pending']:
                raise OSError('disk failure after remote acceptance')
            monitor.save_state(path, state)
        with patch.object(telegram, 'send', return_value=('confirmed', 0)):
            with self.assertRaises(OSError):
                telegram.deliver(self.state, self.path, TOKEN, 1000, save)
        restored = telegram.load_state(self.path, CONFIG)
        self.assertEqual(restored['pending'][0]['status'], 'uncertain')
        self.deliver(('confirmed', 0), state=restored).assert_not_called()

    def test_timeout_is_held_but_new_recovery_can_deliver(self):
        self.deliver(('uncertain', 0))
        restored = telegram.load_state(self.path, CONFIG)
        self.deliver(('confirmed', 0), state=restored).assert_not_called()
        telegram.enqueue(restored, ['RECOVERED [disk] private detail'], {}, 1001)
        self.deliver(('confirmed', 0), state=restored).assert_called_once()
        self.assertEqual(len(restored['pending']), 1)
        self.assertEqual(restored['pending'][0]['status'], 'uncertain')

    def test_429_delay_and_three_attempt_budget_survive_restart(self):
        item_id = self.state['pending'][0]['id']
        self.deliver(('rate_limited', 900))
        for attempt in (2, 3):
            self.state = telegram.load_state(self.path, CONFIG)
            item = self.state['pending'][0]
            self.assertEqual(item['id'], item_id)
            self.assertGreaterEqual(item['retry_at'], 1900)
            self.deliver(('confirmed', 0), now=item['retry_at'] - 1).assert_not_called()
            self.deliver(('rate_limited', 900), now=item['retry_at'])
            self.assertEqual(item['attempts'], attempt)
        self.assertEqual(item['status'], 'blocked')
        self.deliver(('confirmed', 0), now=100000).assert_not_called()

    def test_wrong_destination_corrupt_state_and_injected_body_fail_closed(self):
        with self.assertRaises(ValueError):
            telegram.load_state(self.path, {**CONFIG, 'chat_id': '999'})
        self.state['pending'][0]['summary'] = TOKEN
        monitor.save_state(self.path, self.state)
        with self.assertRaises(ValueError):
            telegram.load_state(self.path, CONFIG)
        self.path.write_text('not json')
        with self.assertRaises(ValueError):
            telegram.load_state(self.path, CONFIG)

    def test_oversized_and_non_json_responses_are_uncertain(self):
        for raw in (b'x' * 65537, b'not json'):
            with patch.object(telegram.urllib.request, 'build_opener') as build:
                build.return_value.open.return_value = io.BytesIO(raw)
                self.assertEqual(telegram.send(TOKEN, CONFIG['chat_id'], 'summary'), ('uncertain', 0))
    def test_queue_limit_preserves_previous_reminder_state(self):
        self.state['pending'] *= telegram.MAX_PENDING
        with self.assertRaises(RuntimeError):
            telegram.enqueue(self.state, ['CRITICAL [disk] problem'], {'disk': {}}, 1000)
        self.assertEqual(self.state['checks'], {})


class TelegramConfiguration(unittest.TestCase):
    def test_recipient_must_be_single_positive_private_id_and_enabled_boolean(self):
        for field, value in [('chat_id', '-100123'), ('chat_id', '@owner'), ('chat_id', '*'),
                             ('chat_id', ['123']), ('bot_id', ''), ('enabled', 'false')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                telegram.validate_config({**CONFIG, field: value})

    def test_credentials_are_private_regular_files_bound_to_bot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private.json'
            path.write_text(json.dumps({'bot_token': TOKEN}))
            path.chmod(0o600)
            self.assertEqual(telegram.load_credentials(path, '123456'), TOKEN)
            with self.assertRaises(ValueError):
                telegram.load_credentials(path, '999')
            path.chmod(0o644)
            with self.assertRaises(PermissionError):
                telegram.load_credentials(path, '123456')
            link = Path(directory) / 'symlink'
            link.symlink_to(path)
            with self.assertRaises(OSError):
                telegram.load_credentials(link, '123456')
            fifo = Path(directory) / 'pipe'
            monitor.os.mkfifo(fifo, 0o600)
            with self.assertRaises(PermissionError):
                telegram.load_credentials(fifo, '123456')


class MonitorIntegration(unittest.TestCase):
    def test_alert_reminder_and_recovery_use_separate_queue_with_matrix_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'reminder_hours': 6, 'notification': {
                'type': 'matrix', 'credentials_file': 'matrix.json', 'telegram': CONFIG}}
            (root / 'matrix.json').write_text('{}')
            (root / 'matrix.json').chmod(0o600)
            (root / CONFIG['credentials_file']).write_text(json.dumps({'bot_token': TOKEN}))
            (root / CONFIG['credentials_file']).chmod(0o600)
            problem = {'disk': {'level': 'critical', 'message': 'PRIVATE ' + TOKEN}}
            recovery = {'disk': {'level': 'ok', 'message': 'PRIVATE recovery'}}
            output = io.StringIO()
            with patch.object(monitor, 'ROOT', root), contextlib.redirect_stdout(output), \
                 patch.object(monitor, 'collect', side_effect=[problem, problem, problem, recovery]), \
                 patch.object(monitor.time, 'time', side_effect=[1000, 1001, 23000, 23001]), \
                 patch.object(monitor, 'send_matrix') as matrix, \
                 patch.object(telegram, 'send', return_value=('confirmed', 0)) as send:
                for _ in range(4):
                    self.assertEqual(monitor.run_monitor(config, root), 0)
            self.assertEqual(matrix.call_count, 3)
            self.assertEqual(send.call_count, 3)
            self.assertIn('RECOVERED: Disk space', send.call_args.args[2])
            self.assertNotIn(TOKEN, str(send.call_args_list[0].args[2]))
            self.assertEqual(json.loads((root / 'state.json').read_text())['pending'], [])

    def test_bad_telegram_configuration_does_not_block_matrix_and_logs_no_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'matrix.json').write_text('{}')
            (root / 'matrix.json').chmod(0o600)
            config = {'reminder_hours': 6, 'notification': {
                'type': 'matrix', 'credentials_file': 'matrix.json',
                'telegram': {**CONFIG, 'chat_id': TOKEN}}}
            output = io.StringIO()
            with patch.object(monitor, 'ROOT', root), contextlib.redirect_stdout(output), \
                 patch.object(monitor, 'collect', return_value={'disk': {'level': 'critical', 'message': 'problem'}}), \
                 patch.object(monitor, 'send_matrix') as matrix, patch.object(telegram, 'send') as send:
                self.assertEqual(monitor.run_monitor(config, root), 1)
            matrix.assert_called_once()
            send.assert_not_called()
            self.assertNotIn(TOKEN, output.getvalue())

    def test_legacy_matrix_config_creates_no_telegram_state_or_requests(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(telegram, 'send') as send:
            self.assertEqual(monitor.telegram_notifications(
                {'notification': {}}, {}, Path(directory), 1000), 0)
            send.assert_not_called()
            self.assertFalse((Path(directory) / 'telegram.json').exists())

    def test_full_queue_drains_without_advancing_unsaved_reminder_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'telegram.json'
            state = telegram.load_state(path, CONFIG)
            for _ in range(telegram.MAX_PENDING):
                telegram.enqueue(state, ['CRITICAL [disk] problem'], {}, 1000)
            monitor.save_state(path, state)
            config = {'reminder_hours': 6, 'notification': {'telegram': CONFIG}}
            with patch.object(telegram, 'load_credentials', return_value=TOKEN), \
                 patch.object(telegram, 'send', return_value=('confirmed', 0)), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(monitor.telegram_notifications(config,
                    {'disk': {'level': 'critical', 'message': 'problem'}}, root, 1001), 1)
            retained = telegram.load_state(path, CONFIG)
            self.assertEqual(len(retained['pending']), telegram.MAX_PENDING - 1)
            self.assertEqual(retained['checks'], {})

    def test_check_mode_does_not_create_state_or_send_even_when_telegram_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / 'config.json'
            config_path.write_text(json.dumps({'notification': {'type': 'matrix', 'telegram': CONFIG}}))
            state_dir = root / 'unused-state'
            with patch('sys.argv', ['monitor.py', '--check', '--config', str(config_path),
                                    '--state-dir', str(state_dir)]), \
                 patch.object(monitor, 'collect', return_value={'disk': {'level': 'ok', 'message': 'healthy'}}), \
                 patch.object(telegram, 'send') as send, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(monitor.main(), 0)
            send.assert_not_called()
            self.assertFalse(state_dir.exists())

    def test_matrix_failure_does_not_prevent_telegram_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'reminder_hours': 6, 'notification': {
                'type': 'matrix', 'credentials_file': 'missing.json', 'telegram': CONFIG}}
            (root / CONFIG['credentials_file']).write_text(json.dumps({'bot_token': TOKEN}))
            (root / CONFIG['credentials_file']).chmod(0o600)
            with patch.object(monitor, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()), \
                 patch.object(monitor, 'collect', return_value={'disk': {'level': 'critical', 'message': 'problem'}}), \
                 patch.object(telegram, 'send', return_value=('confirmed', 0)) as send:
                self.assertEqual(monitor.run_monitor(config, root), 1)
            send.assert_called_once()
            self.assertEqual(len(json.loads((root / 'state.json').read_text())['pending']), 1)

    def test_overlapping_monitor_invocation_stops_before_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / 'config.json'
            config_path.write_text(json.dumps({'notification': {'type': 'journal'}}))
            with (root / 'monitor.lock').open('a') as lock:
                monitor.fcntl.flock(lock, monitor.fcntl.LOCK_EX | monitor.fcntl.LOCK_NB)
                with patch('sys.argv', ['monitor.py', '--config', str(config_path), '--state-dir', str(root)]), \
                     patch.object(monitor, 'collect') as collect, self.assertRaises(BlockingIOError):
                    monitor.main()
                collect.assert_not_called()


class SyntheticAlertCommand(unittest.TestCase):
    def test_isolated_problem_repeat_and_recovery_are_labeled_and_do_not_collect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / 'config.json'
            config_path.write_text(json.dumps({'reminder_hours': 6, 'notification': {'telegram': CONFIG}}))
            (root / CONFIG['credentials_file']).write_text(json.dumps({'bot_token': TOKEN}))
            (root / CONFIG['credentials_file']).chmod(0o600)
            test_dir = root / 'telegram-test-fixture'
            argv = ['verify', '--config', str(config_path), '--state-dir', str(test_dir), '--phase']
            with patch.object(monitor, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()), \
                 patch.object(telegram, 'send', return_value=('confirmed', 0)) as send, \
                 patch.object(monitor, 'collect') as collect:
                for phase in ('problem', 'problem', 'recovery'):
                    with patch('sys.argv', argv + [phase]):
                        self.assertEqual(verify.main(), 0)
            collect.assert_not_called()
            self.assertEqual(send.call_count, 2)
            self.assertIn('CRITICAL: TEST delivery', send.call_args_list[0].args[2])
            self.assertIn('RECOVERED: TEST delivery', send.call_args_list[1].args[2])
            self.assertFalse((root / 'state.json').exists())

    def test_production_state_path_is_rejected(self):
        with patch('sys.argv', ['verify', '--config', '/unused', '--state-dir',
                               '/var/lib/homelab-monitor', '--phase', 'problem']), \
             patch.object(telegram, 'send') as send, self.assertRaises(ValueError):
            verify.main()
        send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
